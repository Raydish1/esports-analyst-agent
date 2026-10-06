"""The GraphQL query versions the builder reads from the cache, per endpoint (docs/build-plan.md, "What
the cache showed"): the crawl's current queries, plus any older version whose pages were never
fetched again. A response to a version not listed here is skipped, since the builder can't vouch for
its fields. So when a crawl query changes, list its old version here until its pages are re-fetched.
"""

import crawl
from cache import query_hash

STANDINGS = {query_hash(crawl.STANDINGS_QUERY)}
ENTRANTS = {query_hash(crawl.ENTRANTS_QUERY)}
EVENT_SETS = {query_hash(crawl.EVENT_SETS_QUERY)}
POOL_SETS = {query_hash(crawl.POOL_SETS_QUERY)}
PHASE_POOLS = {query_hash(crawl.PHASE_POOLS_QUERY), "4adbea053cfe"}  # the pilot's 7 pages, never fetched again
ROSTER = {query_hash(crawl.CM_ROSTER_QUERY)}
BRACKET = {query_hash(crawl.CM_BRACKET_QUERY)}
