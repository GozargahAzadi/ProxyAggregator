"""Subscription generation (Phase 8) and deterministic publishing (Phase 9).

Phase 8 (`feeds`) turns ranked, eligible proxies into deterministic feeds.
Phase 9 (`publisher`) turns those feeds into byte-exact artifact files plus a
deterministic release manifest, and `samples` provides synthetic demo feeds
for a local dry run. Clash and sing-box formats are deferred (see
``docs/SUBSCRIPTION.md``); their publishing is likewise deferred.
"""

from proxyaggregator.publishing.errors import SubscriptionError
from proxyaggregator.publishing.feeds import build_protocol_subscriptions, build_subscription
from proxyaggregator.publishing.models import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
    SubscriptionRequest,
)
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROTOCOL_FILENAME_STEMS,
    MANIFEST_FILENAME,
    PublishError,
    SubscriptionRelease,
    build_release_manifest,
    default_filename,
    default_protocol_filename,
    publish_subscriptions,
    write_artifact,
    write_release_manifest,
)
from proxyaggregator.publishing.samples import build_demo_subscriptions
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS, canonical_uri

__all__ = [
    "DEFAULT_FILENAMES",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_PROTOCOL_FILENAME_STEMS",
    "MANIFEST_FILENAME",
    "SUPPORTED_PROTOCOLS",
    "PublishError",
    "RankedProxy",
    "Subscription",
    "SubscriptionError",
    "SubscriptionFormat",
    "SubscriptionRelease",
    "SubscriptionRequest",
    "build_demo_subscriptions",
    "build_protocol_subscriptions",
    "build_release_manifest",
    "build_subscription",
    "canonical_uri",
    "default_filename",
    "default_protocol_filename",
    "publish_subscriptions",
    "write_artifact",
    "write_release_manifest",
]
