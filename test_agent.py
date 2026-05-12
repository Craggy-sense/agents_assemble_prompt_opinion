import asyncio
from google.adk.agents import Agent
from ecc_agent.agent import root_agent

async def run():
    try:
        response = await root_agent.run("Hello")
        print("Success:", response)
    except Exception as e:
        print("Error:", e)

asyncio.run(run())
