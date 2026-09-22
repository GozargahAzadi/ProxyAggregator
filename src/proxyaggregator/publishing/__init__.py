"""Subscription generation (Phase 8).

Given Phase 7 ranked, eligible proxies, produces deterministic subscription
feeds: a plain canonical URI list, a standard Base64 subscription, and a
deterministic JSON feed. Clash and sing-box config formats are deferred (see
``docs/SUBSCRIPTION.md``); publishing those files happens in Phase 9.
"""

from proxyaggregator.publishing.errors import SubscriptionError
from proxyaggregator.publishing.feeds import build_subscription
from proxyaggregator.publishing.models import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
    SubscriptionRequest,
)
from proxyaggregator.publishing.serializer import canonical_uri

__all__ = [
    "RankedProxy",
    "Subscription",
    "SubscriptionError",
    "SubscriptionFormat",
    "SubscriptionRequest",
    "build_subscription",
    "canonical_uri",
]
