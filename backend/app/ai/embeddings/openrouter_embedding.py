"""Text-only embeddings; never mix these vectors with image embeddings."""
import math
import httpx


class EmbeddingError(RuntimeError):
    def __init__(self,message,status_code=None):
        super().__init__(message)
        self.status_code=status_code


class OpenRouterTextEmbedder:
    def __init__(self, settings, transport=None):
        self.model = settings.text_embed_model
        self.dim = settings.text_embed_dim
        self.batch_size = settings.text_embed_batch_size
        self.has_key = bool(settings.openrouter_api_key)
        key = settings.openrouter_api_key.get_secret_value() if self.has_key else ''
        self.http = httpx.Client(base_url=settings.openrouter_base_url.rstrip('/'),
            headers={'Authorization': 'Bearer '+key},
            timeout=httpx.Timeout(settings.openrouter_timeout_s, connect=min(10,settings.openrouter_timeout_s)), transport=transport)

    def embed_texts(self, texts):
        if not texts or any(not isinstance(t, str) or not t.strip() or len(t)>16000 for t in texts):
            raise ValueError('Provide nonempty text inputs up to 16000 characters each')
        if not self.has_key:
            raise EmbeddingError('OPENROUTER_API_KEY is not configured')
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start+self.batch_size]
            try:
                response = self.http.post('/embeddings', json={'model': self.model,
                    'input': batch, 'dimensions': self.dim, 'encoding_format': 'float',
                    'provider': {'data_collection': 'deny', 'require_parameters': True}})
            except httpx.TimeoutException:
                raise EmbeddingError('Embedding provider timed out',504) from None
            except httpx.HTTPError:
                raise EmbeddingError('Embedding provider connection failed') from None
            if response.status_code != 200:
                raise EmbeddingError(f'Embedding provider HTTP {response.status_code}',response.status_code)
            try:
                rows = response.json()['data']
                if len(rows) != len(batch) or sorted(r['index'] for r in rows) != list(range(len(batch))):
                    raise ValueError()
                for row in sorted(rows, key=lambda r: r['index']):
                    vector = row['embedding']
                    if len(vector) != self.dim or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):
                        raise ValueError()
                    norm = math.sqrt(sum(v*v for v in vector))
                    if not math.isfinite(norm) or norm == 0:
                        raise ValueError()
                    vectors.append([v/norm for v in vector])
            except (ValueError, KeyError, TypeError):
                raise EmbeddingError('Invalid embedding response or dimensions') from None
        return vectors

    def close(self):
        self.http.close()
