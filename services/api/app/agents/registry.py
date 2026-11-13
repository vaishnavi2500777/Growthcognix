from app.agents import competitor_analysis, customer_persona, market_research
from app.agents.runtime import AgentFn

AGENTS: dict[str, AgentFn] = {
    market_research.SLUG: market_research.run,
    competitor_analysis.SLUG: competitor_analysis.run,
    customer_persona.SLUG: customer_persona.run,
}
