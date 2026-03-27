import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def groq_complete(prompt, system_prompt=None, history=[], **kwargs) -> str:
    """OpenAI-compatible wrapper for Groq LLM"""
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    for msg in history:
        messages.append(msg)
        
    messages.append({"role": "user", "content": prompt})
    
    allowed_params = ["model", "messages", "temperature", "max_tokens", "top_p", "stream", "stop"]
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}
    
    model = "openai/gpt-oss-20b"
    
    try:
        print(f"Calling Groq with model: {model}...")
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            **filtered_kwargs
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return str(e)

async def main():
    res = await groq_complete("Hello, say 'INDRA' is active.")
    print(f"Response: {res}")

if __name__ == "__main__":
    asyncio.run(main())
