"""Subscription generation (Phase 8), publishing (Phase 9), and naming (Phase 10).

Phase 8 (`feeds`) turns ranked, eligible proxies into deterministic feeds.
Phase 9 (`publisher`) turns those feeds into byte-exact artifact files plus a
deterministic release manifest, and `samples` provides synthetic demo feeds
for a local dry run. Phase 10 (`naming`) stamps every published node with a
deterministic public Remark. Clash and sing-box formats are deferred (see
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
from proxyaggregator.publishing.naming import (
    PROTOCOL_DISPLAY_NAMES,
    REMARK_AUTHOR,
    build_remark,
    country_flag,
    format_latency_ms,
    normalize_country_code,
    protocol_display_name,
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
    "PROTOCOL_DISPLAY_NAMES",
    "REMARK_AUTHOR",
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
    "build_remark",
    "build_subscription",
    "canonical_uri",
    "country_flag",
    "default_filename",
    "default_protocol_filename",
    "format_latency_ms",
    "normalize_country_code",
    "protocol_display_name",
    "publish_subscriptions",
    "write_artifact",
    "write_release_manifest",
]
