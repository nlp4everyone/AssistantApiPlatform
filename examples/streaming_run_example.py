from openai import OpenAI

# Initialize OpenAI client with local ChatEngine endpoint
client = OpenAI(base_url="http://localhost:8005/v1",
                api_key="token")

# Create a new assistant with math tutoring capabilities
my_assistant = client.beta.assistants.create(
    instructions="You are a personal math tutor. When asked a question, write and run Python code to answer the question.",
    name="Math Tutor",
    tools=[{"type": "code_interpreter"}],
    model="gpt-4o",
)

print("\n" + "="*50)
print("🤖 CREATED ASSISTANT")
print("="*50)
print(f"Assistant ID: {my_assistant.id}")
print("="*50 + "\n")


# Create and run a thread with streaming
print("\n" + "="*50)
print("🚀 STARTING STREAMING RUN")
print("="*50)
print("Creating thread and running assistant with streaming...")
print("="*50 + "\n")

stream = client.beta.threads.create_and_run(
  assistant_id=my_assistant.id,
  thread={
    "messages": [
      {"role": "user", "content": "Explain deep learning to a 5 year old."}
    ]
  },
  stream=True,
  temperature=0
)

print("\n" + "="*50)
print("📡 STREAMING EVENTS")
print("="*50)
for event in stream:
    print(f"Event: {event}")
print("="*50 + "\n")