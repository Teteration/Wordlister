import unittest

from wordlister_core.extractors.headers import extract_headers
from wordlister_core.extractors.html import extract_html
from wordlister_core.extractors.json_data import extract_json_text
from wordlister_core.extractors.url import extract_url


class UrlExtractorTests(unittest.TestCase):
    def test_extracts_host_path_query_fragment_and_nested_url(self) -> None:
        words = extract_url(
            "https://api-staging.example.com/userProfiles/getUser.json"
            "?debug=&redirect=%2Fadmin%2Freset-password#accountRecovery"
        )

        self.assertTrue(
            {
                "api-staging",
                "api",
                "staging",
                "example",
                "userProfiles",
                "user",
                "Profiles",
                "getUser",
                "get",
                "User",
                "json",
                "debug",
                "redirect",
                "admin",
                "reset-password",
                "reset",
                "password",
                "accountRecovery",
                "account",
                "Recovery",
            }.issubset(words)
        )

    def test_keeps_sensitive_parameter_name_but_drops_its_value(self) -> None:
        words = extract_url("https://example.com/login?access_token=DoNotExposeThisSecret123")

        self.assertIn("access_token", words)
        self.assertIn("access", words)
        self.assertIn("token", words)
        self.assertNotIn("DoNotExposeThisSecret123", words)


class HtmlExtractorTests(unittest.TestCase):
    def test_extracts_attributes_urls_comments_json_and_inline_javascript(self) -> None:
        html = """
        <html>
          <body>
            <!-- legacyAdminExport -->
            <form id="resetPasswordForm" action="/account/reset-password">
              <input type="password" name="newPassword" value="DoNotLeakPassword123">
              <button data-endpoint="/api/account/verify">Verify account</button>
            </form>
            <script type="application/json">
              {"featureName": "securityDashboard", "csrfToken": "DoNotLeakCsrf123"}
            </script>
            <script src="/assets/application.js"></script>
            <script>const reportEndpoint = "/api/reports/monthly-summary";</script>
          </body>
        </html>
        """

        words = extract_html(html, "https://example.com/start", include_comments=True)

        self.assertTrue(
            {
                "resetPasswordForm",
                "reset",
                "Password",
                "Form",
                "account",
                "reset-password",
                "newPassword",
                "data-endpoint",
                "api",
                "verify",
                "legacyAdminExport",
                "featureName",
                "securityDashboard",
                "csrfToken",
                "reportEndpoint",
                "reports",
                "monthly-summary",
                "assets",
                "application",
            }.issubset(words)
        )
        self.assertNotIn("DoNotLeakPassword123", words)
        self.assertNotIn("DoNotLeakCsrf123", words)
        self.assertIn("form.action", words.sources["reset-password"])
        self.assertIn("json.key", words.sources["featureName"])
        self.assertIn("javascript.declaration", words.sources["reportEndpoint"])
        self.assertIn("html.src", words.sources["application"])


class JsonExtractorTests(unittest.TestCase):
    def test_extracts_nested_keys_and_safe_values(self) -> None:
        payload = """
        {
          "userProfile": {
            "accountStatus": "pendingVerification",
            "resetPasswordUrl": "/account/reset-password",
            "accessToken": "DoNotExposeThisToken123"
          },
          "allowedActions": ["updateProfile", "deleteAccount"]
        }
        """

        words = extract_json_text(payload, base_url="https://example.com/api")

        self.assertTrue(
            {
                "userProfile",
                "user",
                "Profile",
                "accountStatus",
                "pendingVerification",
                "resetPasswordUrl",
                "reset-password",
                "accessToken",
                "allowedActions",
                "updateProfile",
                "deleteAccount",
            }.issubset(words)
        )
        self.assertNotIn("DoNotExposeThisToken123", words)


class HeaderExtractorTests(unittest.TestCase):
    def test_extracts_safe_response_metadata_without_cookie_values(self) -> None:
        headers = {
            "Location": "/account/dashboard?returnUrl=/admin/reports",
            "Set-Cookie": "admin_session=DoNotLeakCookie123; Path=/control-panel; HttpOnly",
            "Content-Disposition": 'attachment; filename="monthly-report.xlsx"',
            "Access-Control-Allow-Headers": "X-API-Key, X-Client-Version",
        }

        words = extract_headers(headers, "https://example.com/login")

        self.assertTrue(
            {
                "Location",
                "account",
                "dashboard",
                "returnUrl",
                "admin",
                "reports",
                "admin_session",
                "control-panel",
                "monthly-report",
                "xlsx",
                "X-API-Key",
                "X-Client-Version",
            }.issubset(words)
        )
        self.assertNotIn("DoNotLeakCookie123", words)


if __name__ == "__main__":
    unittest.main()
