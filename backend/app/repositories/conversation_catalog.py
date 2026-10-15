"""Read-only catalog snapshots; price ordering is performed by PostgreSQL."""
from sqlalchemy import text
from app.core.errors import ApiError


class ConversationCatalogRepository:
    def __init__(self,retrieval):self.retrieval=retrieval

    def read(self,plan=None,limits=None):
        clauses=[];params={}
        if plan:
            if plan.requires_price:clauses+=['price IS NOT NULL',"currency='THB'"]
            if plan.allowed_ids is not None:
                clauses.append('id = ANY(CAST(:ids AS uuid[]))');params['ids']=[str(i) for i in plan.allowed_ids]
            for field,values in (('category',plan.categories),('brand',plan.brands)):
                if values:
                    keys=[]
                    for i,v in enumerate(values):key=f'{field}{i}';params[key]=v;keys.append(':'+key)
                    clauses.append(field+' IN ('+','.join(keys)+')')
            if limits:
                clauses.append("price IS NOT NULL AND currency='THB' AND price BETWEEN :low AND :high")
                params.update(low=limits[0],high=limits[1])
        order='price '+('DESC' if plan and plan.order=='desc' else 'ASC')+',id ASC' if plan and plan.order else 'id ASC'
        statement='SELECT * FROM products'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY '+order+' LIMIT 5001'
        with self.retrieval.connection() as conn:rows=[dict(r) for r in conn.execute(text(statement),params).mappings()]
        if len(rows)>5000:raise ApiError(503,'CATALOG_QUERY_LIMIT','catalog query exceeds bounded scan size')
        return rows
