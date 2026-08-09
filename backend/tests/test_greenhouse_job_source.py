from __future__ import annotations

import httpx

from app import foreign_job_fetcher


async def test_greenhouse_public_jobs_are_normalized_with_source_attribution(monkeypatch):
    monkeypatch.setenv("GREENHOUSE_BOARDS", "example:Example Co")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["content"] == "true"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "Data Scientist",
                        "absolute_url": "https://boards.greenhouse.io/example/jobs/1",
                        "location": {"name": "New York"},
                        "content": "<p>Build forecasting models &amp; explain trade-offs.</p>",
                        "departments": [{"name": "Data"}],
                        "offices": [],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await foreign_job_fetcher.fetch_greenhouse_jobs(client)

    assert len(jobs) == 1
    assert jobs[0]["company_name"] == "Example Co"
    assert jobs[0]["source_name"] == "Greenhouse · Example Co"
    assert jobs[0]["source_url"].endswith("/jobs/1")
    assert "Build forecasting models" in jobs[0]["responsibilities"][0]
