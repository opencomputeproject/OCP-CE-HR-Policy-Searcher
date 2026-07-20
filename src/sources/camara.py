"""Brazil Câmara dos Deputados structured policy source.

Brazil is a fast-growing data-centre market (the "Redata" tax-incentive
push) with no coverage here before this client. The Câmara open-data API
has real server-side keyword search — a nonsense keyword returns zero
rows, verified live 2026-07-17 — but it matches INDEXED keywords, not full
text, so several complementary terms are queried.

Term-selection evidence from the same probe: "eficiência energética" 17
hits, "centro de dados" 2, "datacenter" 1, "calor residual" 0 (kept anyway
— it is the exact domain phrase and costs one request). Plain "calor" is
poisoned: it returns workplace-heat allowance bills (adicional de
insalubridade por calor externo), not energy policy.

The Senado's equivalent service is deliberately NOT included: its old XML
API self-declares deprecation and its replacement ignored keyword filters
when probed (see the source catalog).

License: Câmara open data, free with attribution.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

LIST_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
DETAIL_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes/{id}"
PUBLIC_URL = (
    "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao"
    "?idProposicao={id}"
)

DEFAULT_TERMS = [
    "calor residual",
    "centro de dados",
    "datacenter",
    "eficiência energética",
]
DEFAULT_MAX_DOCUMENTS = 25
PER_TERM_RECORDS = 25


def _lifecycle(situacao: str) -> str | None:
    """Stage from descricaoSituacao, claimed conservatively.

    "Transformado/a em ..." (law/norm) is an explicit enactment statement.
    "Arquivada" can mean rejected, superseded or shelved — claim nothing
    and let the analysis model read the record. Anything else is a live
    proposal somewhere in committee.
    """
    lowered = (situacao or "").lower()
    if not lowered:
        return None
    if "transformado em" in lowered or "transformada em" in lowered:
        return "enacted"
    if "arquivad" in lowered:
        return None
    return "proposed"


@register_source
class CamaraSource(PolicySource):
    """Fetches Brazilian legislative proposals from dadosabertos.camara.leg.br."""

    id = "camara"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_ids: set[int] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for prop in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, prop, seen_ids)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                LIST_URL,
                params={
                    "keywords": term,
                    "itens": PER_TERM_RECORDS,
                    "ordem": "DESC",
                    "ordenarPor": "id",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Câmara search failed for %r: %s", term, e)
            return []

        props = data.get("dados") if isinstance(data, dict) else None
        return [p for p in props if isinstance(p, dict)] if isinstance(props, list) else []

    async def _detail(self, client: httpx.AsyncClient, prop_id: int) -> dict:
        try:
            resp = await client.get(DETAIL_URL.format(id=prop_id))
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Câmara detail failed for %s: %s", prop_id, e)
            return {}
        dados = data.get("dados") if isinstance(data, dict) else None
        return dados if isinstance(dados, dict) else {}

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, prop: dict, seen_ids: set[int]
    ) -> CrawlResult | None:
        prop_id = prop.get("id")
        if prop_id is None:
            return None
        if prop_id in seen_ids:
            return None
        seen_ids.add(prop_id)

        detail = await self._detail(client, prop_id)

        sigla = detail.get("siglaTipo") or prop.get("siglaTipo") or ""
        numero = detail.get("numero") or prop.get("numero") or ""
        ano = detail.get("ano") or prop.get("ano") or ""
        title = f"{sigla} {numero}/{ano}".strip()

        ementa = detail.get("ementa") or prop.get("ementa") or ""

        meta = []
        presented = (detail.get("dataApresentacao")
                     or prop.get("dataApresentacao") or "")[:10]
        if presented:
            meta.append(f"Apresentação: {presented}.")
        tipo = detail.get("descricaoTipo")
        if tipo:
            meta.append(f"Tipo: {tipo}.")
        status = detail.get("statusProposicao") or {}
        situacao = status.get("descricaoSituacao") or ""
        if situacao:
            meta.append(f"Situação: {situacao}.")
        despacho = status.get("despacho")
        if despacho:
            meta.append(f"Despacho: {despacho}")
        keywords = detail.get("keywords")
        if keywords:
            meta.append(f"Palavras-chave: {keywords}.")

        content = "\n\n".join(p for p in (
            title,
            ementa,
            detail.get("ementaDetalhada") or "",
            " ".join(meta),
        ) if p and p.strip())
        if not content:
            return None

        return CrawlResult(
            url=PUBLIC_URL.format(id=prop_id),
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=_lifecycle(situacao) if status else None,
        )
