# ThingsBoard Alarm Setup Assistant

This program allows you to interact with a language model (LLM) to automate the process of creating and managing ThingsBoard rule chains and alarms using natural language commands.

## Prerequisites

1. **ThingsBoard Instance**: Ensure your ThingsBoard instance is running and accessible.
2. **Environment Variables**: Create a `.env` file in the same directory as `withchat.py` and `cli.py` with the following content:

```env
OPENAI_PROJECT_API_KEY=*********************************************yours
OPENAI_API_KEY=OPENAI_PROJECT_API_KEY

# ThingsBoard Settings
THINGSBOARD_URL=http://localhost:8080
THINGSBOARD_USERNAME=tenant@thingsboard.org
THINGSBOARD_PASSWORD=tenant
ROOT_RULE_CHAIN_ID=cf80ba30-1847-11f0-9b77-45d09c1e5989

3. run python cli.py
