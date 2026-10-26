import unittest

from wordlister_core.extractors.headers import extract_headers
from wordlister_core.extractors.html import extract_html
from wordlister_core.extractors.javascript import extract_javascript
from wordlister_core.extractors.json_data import extract_json_text
from wordlister_core.extractors.url import extract_url


class UrlExtractorTests(unittest.TestCase):
    def test_extracts_paths_query_names_and_nested_url_paths(self) -> None:
        words = extract_url(
            "https://api-staging.example.com/userProfiles/getUser.json"
            "?debug=&redirect=%2Fadmin%2Freset-password#accountRecovery"
        )

        self.assertTrue(
            {
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
            }.issubset(words)
        )
        self.assertNotIn("api-staging", words)
        self.assertNotIn("accountRecovery", words)
        self.assertEqual({"url.query.name"}, words.sources["debug"])
        self.assertEqual({"url.query.url"}, words.sources["reset-password"])

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
            <form id="resetPasswordForm" class="marketing-panel" action="/account/reset-password">
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
                "account",
                "reset-password",
                "newPassword",
                "api",
                "verify",
                "legacyAdminExport",
                "featureName",
                "csrfToken",
                "reports",
                "monthly-summary",
            }.issubset(words)
        )
        self.assertNotIn("DoNotLeakPassword123", words)
        self.assertNotIn("DoNotLeakCsrf123", words)
        self.assertIn("form.action", words.sources["reset-password"])
        self.assertIn("form.field.name", words.sources["newPassword"])
        self.assertIn("json.key", words.sources["featureName"])
        self.assertIn("javascript.url", words.sources["monthly-summary"])
        self.assertNotIn("Verify", words)
        self.assertNotIn("resetPasswordForm", words)
        self.assertNotIn("marketing-panel", words)
        self.assertNotIn("securityDashboard", words)
        self.assertNotIn("reportEndpoint", words)
        self.assertNotIn("assets", words)


class JsonExtractorTests(unittest.TestCase):
    def test_extracts_nested_keys_and_url_values(self) -> None:
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
                "resetPasswordUrl",
                "reset-password",
                "accessToken",
                "allowedActions",
            }.issubset(words)
        )
        self.assertNotIn("pendingVerification", words)
        self.assertNotIn("updateProfile", words)
        self.assertNotIn("deleteAccount", words)
        self.assertNotIn("DoNotExposeThisToken123", words)


class JavaScriptExtractorTests(unittest.TestCase):
    def test_extracts_request_parameters_without_generic_ui_object_keys(self) -> None:
        source = """
        const preferences = {theme: "dark", sidebar: true};
        const form = new FormData();
        form.append("accountId", accountId);
        form.set("includeHistory", true);
        localStorage.set("uiTheme", "dark");
        fetch("/api/account/update", {
          method: "POST",
          body: JSON.stringify({displayName: name, "notify-user": enabled})
        });
        axios.post("/api/report", {reportType: type, includeDrafts: true});
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/avatar/upload");
        const query = new URLSearchParams({pageSize: 50, includeDisabled: false});
        """

        words = extract_javascript(source, base_url="https://example.com/")

        for parameter in (
            "accountId",
            "includeHistory",
            "displayName",
            "notify-user",
            "reportType",
            "includeDrafts",
            "pageSize",
            "includeDisabled",
        ):
            self.assertIn(parameter, words)
            self.assertIn("javascript.parameter", words.sources[parameter])
        self.assertNotIn("theme", words)
        self.assertNotIn("sidebar", words)
        self.assertNotIn("uiTheme", words)
        self.assertIn("update", words)
        self.assertIn("report", words)
        self.assertIn("upload", words)


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
                "account",
                "dashboard",
                "returnUrl",
                "admin",
                "reports",
                "admin_session",
                "control-panel",
                "X-API-Key",
                "X-Client-Version",
            }.issubset(words)
        )
        self.assertNotIn("Location", words)
        self.assertNotIn("monthly-report", words)
        self.assertEqual({"header.value"}, words.sources["X-API-Key"])
        self.assertNotIn("DoNotLeakCookie123", words)


if __name__ == "__main__":
    unittest.main()
