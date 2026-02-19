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


# Retrieve the assistant details using its ID
retrieved_assistant = client.beta.assistants.retrieve(my_assistant.id)

print("\n" + "="*50)
print("🔍 RETRIEVED ASSISTANT")
print("="*50)
print(f"Assistant ID: {retrieved_assistant.id}")
print("="*50 + "\n")


# List all available assistants with pagination
list_assistants = client.beta.assistants.list(
    order="desc",
    limit="20",
)

print("\n" + "="*50)
print("📋 AVAILABLE ASSISTANTS")
print("="*50)
if list_assistants.data:
    for i, assistant in enumerate(list_assistants.data, 1):
        print(f"{i}. {assistant.name} (ID: {assistant.id})")
else:
    print("No assistants found.")
print("="*50 + "\n")


# Delete the assistant to clean up resources
response = client.beta.assistants.delete(my_assistant.id)
print(f"Deleted assistant: {response}")