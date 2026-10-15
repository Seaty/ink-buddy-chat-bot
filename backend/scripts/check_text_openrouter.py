"""Small paid smoke check; prints metadata only, no secrets or embeddings."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder
from app.ai.llm.openrouter_client import OpenRouterClient

s=Settings()
print('Key configured:', bool(s.openrouter_api_key))
e=OpenRouterTextEmbedder(s)
try:
    vectors=e.embed_texts(['ปากกาเจลสำหรับจดโน้ต'])
    print('Embedding model:', e.model, 'returned dimensions:', len(vectors[0]))
finally:
    e.close()
c=OpenRouterClient(s.openrouter_api_key.get_secret_value(), s.openrouter_base_url, s.openrouter_timeout_s, retries=0)
try:
    result=c.chat(s.text_chat_model, [{'role':'user','content':'Reply only OK. /no_think'}], options={'num_predict':128})
    print('Chat model:',result['model'],'nonempty:',bool(result['message']['content']), 'input tokens:',result['prompt_eval_count'],'output tokens:',result['eval_count'])
finally:
    c.close()
