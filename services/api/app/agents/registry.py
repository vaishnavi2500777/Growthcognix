from app.agents import market_research
from app.agents.runtime import AgentFn

AGENTS: dict[str, AgentFn] = {market_research.SLUG: market_research.run}
