from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.collect import CollectionRequest
from app.services.collection_safety import policy_from_env, validate_collection_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a collection request is safe.")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--city", default="上海")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--profile-dir")
    parser.add_argument("--copy-login-state", action="store_true")
    parser.add_argument("--use-main-browser-profile", action="store_true")
    parser.add_argument("--auto-apply", action="store_true")
    parser.add_argument("--auto-message", action="store_true")
    args = parser.parse_args()

    request = CollectionRequest(
        keyword=args.keyword,
        city=args.city,
        pages=args.pages,
        cdp_port=args.cdp_port,
        profile_dir=args.profile_dir,
        copy_login_state=args.copy_login_state,
        use_main_browser_profile=args.use_main_browser_profile,
        auto_apply=args.auto_apply,
        auto_message=args.auto_message,
    )
    result = validate_collection_request(request, policy_from_env())
    print(
        json.dumps(
            {
                "allowed": result.allowed,
                "reasons": list(result.reasons),
                "warnings": list(result.warnings),
                "effective_profile_dir": result.effective_profile_dir,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
