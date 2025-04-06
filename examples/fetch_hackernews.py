import asyncio
from nodetool.dsl.graph import graph, run_graph
from nodetool.dsl.lib.network.http import GetRequest
from nodetool.dsl.nodetool.text import (
    FindAllRegex,
)
from nodetool.dsl.nodetool.output import ListOutput

# Create the workflow graph
g = ListOutput(
    name="hn_stories",
    value=FindAllRegex(
        text=GetRequest(url="https://news.ycombinator.com"),
        regex=r'<span class="titleline"><a href="[^"]*">([^<]+)</a>',  # Extract story titles within titleline span
    ),
)

# Run the graph
print(asyncio.run(run_graph(graph(g))))
