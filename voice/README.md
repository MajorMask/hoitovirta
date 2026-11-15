# voice/
Voice line for Hoitovirta (ElevenLabs agent + FastAPI webhooks). Spec: the voice service spec.
- Offline test: `python3 voice/test_service.py`
- Run locally: `uvicorn voice.service:app --port 8001`
- Create agent: `python3 voice/create_agent.py --base-url https://<url>/voice`
Synthetic data only. The service never writes T0.
