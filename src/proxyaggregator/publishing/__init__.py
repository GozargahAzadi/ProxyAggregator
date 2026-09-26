"""Subscription generation (Phase 8), publishing (Phase 9), and naming (Phase 10).

Phase 8 (`feeds`) turns ranked, eligible proxies into deterministic feeds.
Phase 17 (`countries`) turns the same inputs into per-country feed
directories with generated READMEs. Phase 9 (`publisher`) turns those feeds
into byte-exact artifact files plus a deterministic release manifest, and
`samples` provides synthetic demo feeds for a local dry run. Phase 10
(`naming`) stamps every published node with a deterministic public Remark.
Clash and sing-box formats are deferred (see ``docs/SUBSCRIPTION.md``); their
publishing is likewise deferred.
"""

from proxyaggregator.publishing.countries import (
    COUNTRY_RAW_SUBSCRIPTIONS_BASE_URL,
    build_country_artifacts,
)
from proxyaggregator.publishing.errors import SubscriptionError
from proxyaggregator.publishing.feeds import (
    build_protocol_subscriptions,
    build_subscription,
)
from proxyaggregator.publishing.models import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
    SubscriptionRequest,
)
from proxyaggregator.publishing.naming import (
    COUNTRY_NAMES,
    COUNTRY_UNKNOWN_BUCKET,
    PROTOCOL_DISPLAY_NAMES,
    REMARK_AUTHOR,
    build_remark,
    country_bucket,
    country_code_to_flag,
    country_code_to_name,
    country_flag,
    format_latency_ms,
    normalize_country_code,
    protocol_display_name,
)
from proxyaggregator.publishing.publisher import (
    COUNTRIES_DIR,
    DEFAULT_FILENAMES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROTOCOL_FILENAME_STEMS,
    MANIFEST_FILENAME,
    PublishError,
    ReleaseVerificationError,
    SubscriptionRelease,
    build_release_manifest,
    canonical_artifact_filenames,
    country_all_path,
    country_dir_name,
    country_dir_path,
    country_index_path,
    country_protocol_path,
    country_readme_path,
    default_filename,
    default_protocol_filename,
    publish_release,
    publish_subscriptions,
    verify_release,
    write_artifact,
    write_release_manifest,
)
from proxyaggregator.publishing.samples import build_demo_subscriptions
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS, canonical_uri

__all__ = [
    "COUNTRIES_DIR",
    "COUNTRY_NAMES",
    "COUNTRY_RAW_SUBSCRIPTIONS_BASE_URL",
    "COUNTRY_UNKNOWN_BUCKET",
    "DEFAULT_FILENAMES",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_PROTOCOL_FILENAME_STEMS",
    "MANIFEST_FILENAME",
    "PROTOCOL_DISPLAY_NAMES",
    "REMARK_AUTHOR",
    "SUPPORTED_PROTOCOLS",
    "PublishError",
    "RankedProxy",
    "ReleaseVerificationError",
    "Subscription",
    "SubscriptionError",
    "SubscriptionFormat",
    "SubscriptionRelease",
    "SubscriptionRequest",
    "build_country_artifacts",
    "build_demo_subscriptions",
    "build_protocol_subscriptions",
    "build_release_manifest",
    "build_remark",
    "build_subscription",
    "canonical_artifact_filenames",
    "canonical_uri",
    "country_all_path",
    "country_bucket",
    "country_code_to_flag",
    "country_code_to_name",
    "country_dir_name",
    "country_dir_path",
    "country_flag",
    "country_index_path",
    "country_protocol_path",
    "country_readme_path",
    "default_filename",
    "default_protocol_filename",
    "format_latency_ms",
    "normalize_country_code",
    "protocol_display_name",
    "publish_release",
    "publish_subscriptions",
    "verify_release",
    "write_artifact",
    "write_release_manifest",
]
