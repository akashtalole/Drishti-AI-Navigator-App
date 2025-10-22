#!/usr/bin/env python3
"""
Nova Sonic Speech-to-Speech Example
Demonstrates bidirectional streaming for real-time voice conversations
"""

import asyncio
import base64
import logging
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from voice_service import VoiceService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_text_to_speech():
    """Test text-to-speech conversion"""
    print("\n=== Testing Text-to-Speech ===\n")
    
    service = VoiceService(
        region="us-west-2",
        voice_provider="nova_sonic",
        voice_model="us.amazon.nova-sonic-v1:0"
    )
    
    # Test greeting
    text = "Hello! I'm your order automation assistant. How can I help you today?"
    print(f"Converting text to speech: {text}")
    
    audio_base64 = await service.text_to_speech(text)
    print(f"✓ Generated audio: {len(audio_base64)} characters (base64)")
    
    # Decode to check size
    audio_bytes = base64.b64decode(audio_base64)
    print(f"✓ Audio size: {len(audio_bytes)} bytes")
    print(f"✓ Duration: ~{len(audio_bytes) / (24000 * 2):.1f} seconds (at 24kHz, 16-bit)")
    
    return audio_base64


async def test_conversation_flow():
    """Test full conversation flow"""
    print("\n=== Testing Conversation Flow ===\n")
    
    service = VoiceService(
        region="us-west-2",
        voice_provider="nova_sonic",
        voice_model="amazon.nova-sonic-v1:0"
    )
    
    # Start conversation
    conversation_id = "test-conversation-001"
    print(f"Starting conversation: {conversation_id}")
    
    greeting = await service.start_conversation(conversation_id)
    print(f"✓ Greeting text: {greeting['text'][:100]}...")
    print(f"✓ Greeting audio: {len(greeting['audio'])} characters (base64)")
    print(f"✓ State: {greeting['state']}")
    
    # Simulate audio input (in real scenario, this would be actual audio from microphone)
    # For testing, we'll use a placeholder
    print("\n--- Simulating user speech input ---")
    print("User says: 'I want to order a laptop'")
    
    # In production, you would capture real audio here
    # For now, we'll skip actual audio processing
    dummy_audio = b'\x00' * 32000  # 1 second of silence at 16kHz, 16-bit
    
    try:
        response = await service.process_speech(conversation_id, dummy_audio)
        print(f"✓ User text: {response.get('user_text', 'N/A')}")
        print(f"✓ Assistant text: {response.get('assistant_text', 'N/A')[:100]}...")
        print(f"✓ Assistant audio: {len(response.get('audio', ''))} characters (base64)")
        print(f"✓ State: {response['state']}")
        print(f"✓ Provider: {response['provider']}")
    except Exception as e:
        print(f"⚠ Speech processing error (expected in test): {e}")
        print("  Note: Actual audio input required for full processing")
    
    # Get conversation state
    state = service.get_conversation_state(conversation_id)
    if state:
        print(f"\n✓ Conversation state:")
        print(f"  - Started: {state['started_at']}")
        print(f"  - State: {state['state']}")
        print(f"  - Order data: {state['order_data']}")
        print(f"  - History items: {len(state['conversation_history'])}")
    
    # End conversation
    service.end_conversation(conversation_id)
    print(f"\n✓ Conversation ended and cleaned up")


async def test_order_summary():
    """Test order summary generation"""
    print("\n=== Testing Order Summary ===\n")
    
    service = VoiceService(
        region="us-west-2",
        voice_provider="nova_sonic",
        voice_model="amazon.nova-sonic-v1:0"
    )
    
    # Start conversation and populate with sample data
    conversation_id = "test-summary-001"
    await service.start_conversation(conversation_id)
    
    # Simulate collected order data
    conversation = service.active_conversations[conversation_id]
    conversation["order_data"] = {
        "product_name": "Dell XPS 15 Laptop",
        "product_url": "https://example.com/laptop",
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "shipping_address": {
            "street": "123 Main St",
            "city": "Seattle",
            "state": "WA",
            "zip": "98101",
            "country": "USA"
        },
        "quantity": 1
    }
    
    # Generate summary
    print("Generating order summary...")
    summary = await service.get_order_summary(conversation_id)
    
    print(f"✓ Summary text:\n{summary['text']}")
    print(f"\n✓ Audio: {len(summary['audio'])} characters (base64)")
    print(f"✓ Ready to submit: {summary['ready_to_submit']}")
    print(f"✓ Order data: {len(summary['order_data'])} fields")
    
    # Cleanup
    service.end_conversation(conversation_id)


async def test_configuration_options():
    """Test different configuration options"""
    print("\n=== Testing Configuration Options ===\n")
    
    # Test with custom voice configuration
    custom_config = {
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
        "output_format": "lpcm",
        "sample_size_bits": 16,
        "channel_count": 1,
        "voice_id": "ruth",  # Different voice
        "encoding": "base64",
    }
    
    service = VoiceService(
        region="us-west-2",
        voice_provider="nova_sonic",
        voice_model="amazon.nova-sonic-v1:0",
        voice_config=custom_config
    )
    
    print("✓ Service initialized with custom config:")
    print(f"  - Voice ID: {service.voice_config['voice_id']}")
    print(f"  - Input sample rate: {service.voice_config['input_sample_rate']} Hz")
    print(f"  - Output sample rate: {service.voice_config['output_sample_rate']} Hz")
    print(f"  - Format: {service.voice_config['output_format']}")
    
    # Test TTS with custom voice
    text = "Testing with Ruth voice"
    audio = await service.text_to_speech(text)
    print(f"✓ Generated audio with Ruth voice: {len(audio)} characters")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Nova Sonic Speech-to-Speech Demo")
    print("=" * 60)
    
    try:
        # Test 1: Text-to-Speech
        await test_text_to_speech()
        
        # Test 2: Conversation Flow
        await test_conversation_flow()
        
        # Test 3: Order Summary
        await test_order_summary()
        
        # Test 4: Configuration Options
        await test_configuration_options()
        
        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
