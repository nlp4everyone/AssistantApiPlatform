from openai import OpenAI

# Initialize OpenAI client with local ChatEngine endpoint
client = OpenAI(base_url="http://localhost:8005/v1",
                api_key="token")

# Create an empty thread for conversation management
empty_thread = client.beta.threads.create()

print("\n" + "="*50)
print("🧵 CREATED THREAD")
print("="*50)
print(f"Thread ID: {empty_thread.id}")
print("="*50 + "\n")


# Retrieve the thread details using its ID
my_thread = client.beta.threads.retrieve(empty_thread.id)

print("\n" + "="*50)
print("🔍 RETRIEVED THREAD")
print("="*50)
print(f"Thread ID: {my_thread.id}")
print("="*50 + "\n")


# Delete the thread to clean up resources
response = client.beta.threads.delete(empty_thread.id)

print("\n" + "="*50)
print("🗑️  DELETED THREAD")
print("="*50)
print(f"Deleted ID: {response.id}")
print(f"Deleted: {response.deleted}")
print("="*50 + "\n")