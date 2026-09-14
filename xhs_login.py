"""Open the dedicated experimental-source profile and wait for a successful login."""
import argparse
from pathlib import Path
import sys
import time
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from importer import XHS_BROWSER, XHS_PROFILE


def main(profile=XHS_PROFILE):
    profile = Path(profile).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    url = "https://www.xiaohongshu.com/"
    try:
        with sync_playwright() as playwright:
            options = {"user_data_dir": str(profile), "headless": False,
                       "viewport": {"width": 1440, "height": 900}}
            if XHS_BROWSER.is_file():
                options["executable_path"] = str(XHS_BROWSER)
            context = playwright.chromium.launch_persistent_context(**options)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(url, wait_until="commit", timeout=60_000)
            except PlaywrightError:
                if page.is_closed():
                    page = context.new_page()
                    page.goto(url, wait_until="commit", timeout=60_000)
            print("LOGIN_WINDOW_OPEN", flush=True)
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise RuntimeError("登录完成前窗口已关闭。")
                try:
                    body = page.locator("body").inner_text(timeout=5000)
                    has_profile = page.locator('a[href*="/user/profile/"]').count() > 0
                    has_login_button = page.get_by_text("登录", exact=True).count() > 0
                    if has_profile and not has_login_button and not any(
                            text in body for text in ("登录后查看", "登录查看更多", "手机号登录")):
                        context.close()
                        print("LOGIN_OK", flush=True)
                        return 0
                except PlaywrightError:
                    pass
                page.wait_for_timeout(1000)
            context.close()
            raise RuntimeError("十分钟内没有检测到登录成功。")
    except Exception as exc:
        print(f"LOGIN_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=XHS_PROFILE)
    raise SystemExit(main(parser.parse_args().profile))
