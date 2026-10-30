def test_web_extract_requires_quote_and_points():
    from app.research.schemas import WebExtract

    item = WebExtract(relevant=True, title='AI Safety', language='en', summary='Safety research',
                      points=['Robustness'], quote='Robustness is evaluated')
    assert item.points == ['Robustness']
    assert item.quote == 'Robustness is evaluated'


def test_universal_search_stage_order():
    from app.research.pipeline import STAGES

    assert STAGES['search'] == ['understand', 'web_plan', 'web_discover', 'web_search', 'web_read', 'web_verify', 'answer']


def test_web_candidate_dedupes_by_normalized_url():
    from app.research.pipeline import dedupe_web_candidates

    rows = [{'url': 'https://Example.com/a#section', 'title': 'A'},
            {'url': 'https://example.com/a', 'title': 'A copy'}]
    assert len(dedupe_web_candidates(rows)) == 1


def test_universal_search_reads_bilingual_pages_and_keeps_only_grounded_rows(monkeypatch):
    import asyncio

    from app import crawl
    from app.db import Conversation, Job, Message, Session
    from app.research.pipeline import Run
    from app.research.schemas import WebExtract

    with Session.begin() as db:
        conversation = Conversation(title='通用搜索')
        db.add(conversation)
        db.flush()
        message = Message(conversation_id=conversation.id, role='user', content='AI safety research')
        db.add(message)
        db.flush()
        job = Job(conversation_id=conversation.id, message_id=message.id, mode='search', plan={
            'plan': {'mode': 'search', 'title': 'AI safety', 'query': 'AI safety', 'language': 'mixed'},
            'folder': 'test-folder',
            'search_queries': [
                {'query': 'AI safety', 'language': 'en', 'purpose': 'research'},
                {'query': '人工智能安全', 'language': 'zh', 'purpose': '研究'},
            ],
        })
        db.add(job)
        db.flush()
        message.job_id = job.id
        job_id = job.id

    async def fake_capture(url, folder, profile='', scrolls=6, timeout=600):
        if 'bing.com/search' in url:
            return crawl.Page(url=url, status='captured', title='Search', text='results', links=[
                {'text': 'English AI Safety', 'url': 'https://example.com/en#part'},
                {'text': 'English duplicate', 'url': 'https://EXAMPLE.com/en/'},
                {'text': '中文人工智能安全', 'url': 'https://example.cn/zh'},
                {'text': 'Unverified', 'url': 'https://example.org/bad'},
            ])
        if 'example.com' in url:
            return crawl.Page(url=url, status='captured', title='English AI Safety', text='Robustness is evaluated in this study.')
        if 'example.cn' in url:
            return crawl.Page(url=url, status='captured', title='中文人工智能安全', text='本文讨论人工智能安全评估。')
        return crawl.Page(url=url, status='captured', title='Unverified', text='No matching citation here.')

    async def fake_structured(schema, prompt, system=None):
        if schema is WebExtract:
            if '人工智能安全评估' in prompt:
                return WebExtract(relevant=True, title='中文人工智能安全', language='zh', published_on='2026年10月28日',
                                  summary='安全评估', points=['评估'], quote='本文讨论人工智能安全评估。')
            if 'Robustness is evaluated' in prompt:
                return WebExtract(relevant=True, title='English AI Safety', language='en', published_on='2026-10-29',
                                  summary='Safety evaluation', points=['Robustness'], quote='Robustness is evaluated in this study.')
            return WebExtract(relevant=True, title='Unverified', language='en', quote='citation absent from page')
        raise AssertionError(schema)

    async def fake_begin(*args, **kwargs):
        return 'test-folder'

    monkeypatch.setattr(crawl, 'capture', fake_capture)
    monkeypatch.setattr(crawl, 'begin', fake_begin)
    monkeypatch.setattr('app.research.pipeline.llm.structured', fake_structured)
    run = Run(job_id)
    asyncio.run(run.web_discover())
    asyncio.run(run.web_search())
    asyncio.run(run.web_read())
    asyncio.run(run.web_verify())
    verified = [row for row in run.state['search_results'] if row['status'] == 'verified']
    assert {row['language'] for row in verified} == {'en', 'zh'}
    assert len(verified) == 2
    assert all('absent' not in row.get('quote', '') for row in verified)
