import unittest

import server


class ProjectPayloadSecurityTests(unittest.TestCase):
    def test_valid_payload_is_accepted(self):
        payload = {
            "name": "Demo",
            "description": "Valid project description",
            "description_en": "Valid project description in English",
            "url": "https://example.com/project",
            "color": "#1ED760",
            "tags": ["Java", "Web"],
        }

        self.assertEqual(
            server.project_payload(payload),
            {
                "name": "Demo",
                "description": "Valid project description",
                "description_en": "Valid project description in English",
                "url": "https://example.com/project",
                "color": "#1ed760",
                "tags": '["Java", "Web"]',
            },
        )

    def test_rejects_script_tag_in_description(self):
        with self.assertRaises(ValueError):
            server.project_payload({
                **self.valid_payload(),
                "description": "<script>alert('x')</script>",
            })

    def test_rejects_javascript_scheme_in_description_en(self):
        with self.assertRaises(ValueError):
            server.project_payload({
                **self.valid_payload(),
                "description_en": "javascript:alert(1)",
            })

    def test_rejects_javascript_scheme_in_url(self):
        with self.assertRaises(ValueError):
            server.project_payload({
                **self.valid_payload(),
                "url": "javascript:alert(1)",
            })

    def test_rejects_html_in_tag(self):
        with self.assertRaises(ValueError):
            server.project_payload({
                **self.valid_payload(),
                "tags": ["<img src=x onerror=alert(1)>"]
            })

    @staticmethod
    def valid_payload():
        return {
            "name": "Demo",
            "description": "Valid project description",
            "description_en": "Valid project description in English",
            "url": "https://example.com/project",
            "color": "#1ED760",
            "tags": ["Java", "Web"],
        }


if __name__ == "__main__":
    unittest.main()
