#!/usr/bin/env python3
"""
Nova Sonic Voice Agent Example
Demonstrates how to use the voice-based order automation with Nova Sonic
"""

import asyncio
import base64
import os
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.voice_service import get_voice_service, VoiceService
from config import get_config_manager


async def demo_nova_sonic():
    """Demonstrate Nova Sonic voice interaction"""
    
    print("=== Nova Sonic Voice Agent Demo ===\n")
    
    # Initialize voice service with Nova Sonic
    voice_service = VoiceService(
        region="us-west-2",
        voice_provider="nova_sonic",
        voice_model="us.amazon.nova-sonic-v1:0",
        voice_config={
            "output_sample_rate": 24000,
            "output_format": "pcm",
            "language": "en-US"
        }
    )
    
    print(f"Voice Provider: {voice_service.voice_provider}")
    print(f"Voice Model: {voice_service.voice_model}\n")
    
    # Start a new conversation
    conversation_id = "demo-conversation-001"
    print(f"Starting conversation: {conversation_id}")
    
    try:
        # Start conversation
        greeting = await voice_service.start_conversation(conversation_id)
        print(f"\n[Assistant]: {greeting['text']}")
        print(f"Audio length: {len(greeting['audio'])} bytes (base64)")
        
        # Save greeting audio
        save_audio(greeting['audio'], "greeting.pcm")
        print("Saved audio to: greeting.pcm")
        
        # Simulate user audio input (in practice, this would be from microphone)
        print("\n[User]: (Speaking: 'I want to order a laptop')")
        # Note: In real implementation, you'd capture this from microphone
        # For demo, we'll show the flow without actual audio
        
        print("\n--- Conversation Flow ---")
        print("1. User speaks → Audio captured")
        print("2. Audio sent to Nova Sonic via converse_stream")
        print("3. Nova Sonic processes and responds with audio")
        print("4. Audio played back to user")
        print("5. Order data extracted and updated")
        
        # Get conversation state
        state = voice_service.get_conversation_state(conversation_id)
        print(f"\nConversation State:")
        print(f"  Current State: {state['state']}")
        print(f"  Order Data: {state['order_data']}")
        print(f"  History Length: {len(state['conversation_history'])}")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        voice_service.end_conversation(conversation_id)
        print(f"\nConversation {conversation_id} ended")


async def demo_polly_fallback():
    """Demonstrate Polly fallback mode"""
    
    print("\n\n=== Polly Fallback Demo ===\n")
    
    # Initialize voice service with Polly
    voice_service = VoiceService(
        region="us-west-2",
        voice_provider="polly",
        voice_config={
            "polly_voice_id": "Joanna",
            "polly_engine": "neural",
            "language": "en-US"
        }
    )
    
    print(f"Voice Provider: {voice_service.voice_provider}")
    print(f"Voice Config: {voice_service.voice_config}\n")
    
    try:
        # Test text-to-speech with Polly
        test_text = "This is a test of the Polly text-to-speech system."
        print(f"Converting text to speech: '{test_text}'")
        
        audio = await voice_service.text_to_speech_polly(test_text)
        print(f"Generated audio length: {len(audio)} bytes (base64)")
        
        # Save audio
        save_audio(audio, "polly_test.mp3", format="mp3")
        print("Saved audio to: polly_test.mp3")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


def save_audio(base64_audio: str, filename: str, format: str = "pcm"):
    """Save base64 encoded audio to file"""
    audio_bytes = base64.b64decode(base64_audio)
    
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    output_path = output_dir / filename
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    
    print(f"   Saved to: {output_path}")
    
    if format == "pcm":
        print(f"   Play with: ffplay -f s16le -ar 24000 -ac 1 {output_path}")
    elif format == "mp3":
        print(f"   Play with: ffplay {output_path}")


async def compare_providers():
    """Compare Nova Sonic and Polly performance"""
    
    print("\n\n=== Provider Comparison ===\n")
    
    test_text = "Hello! How can I help you with your order today?"
    
    # Test Nova Sonic
    print("Testing Nova Sonic...")
    try:
        import time
        
        nova_service = VoiceService(
            region="us-west-2",
            voice_provider="nova_sonic",
            voice_model="us.amazon.nova-sonic-v1:0"
        )
        
        start = time.time()
        nova_audio = await nova_service.text_to_speech_nova_sonic(test_text)
        nova_time = time.time() - start
        
        print(f"  ✓ Nova Sonic: {nova_time:.2f}s, {len(nova_audio)} bytes")
        
    except Exception as e:
        print(f"  ✗ Nova Sonic failed: {e}")
        nova_time = None
    
    # Test Polly
    print("\nTesting Polly...")
    try:
        polly_service = VoiceService(
            region="us-west-2",
            voice_provider="polly"
        )
        
        start = time.time()
        polly_audio = await polly_service.text_to_speech_polly(test_text)
        polly_time = time.time() - start
        
        print(f"  ✓ Polly: {polly_time:.2f}s, {len(polly_audio)} bytes")
        
    except Exception as e:
        print(f"  ✗ Polly failed: {e}")
        polly_time = None
    
    # Comparison
    if nova_time and polly_time:
        print(f"\n📊 Results:")
        print(f"   Nova Sonic: {nova_time:.2f}s")
        print(f"   Polly: {polly_time:.2f}s")
        print(f"   Difference: {abs(nova_time - polly_time):.2f}s")
        faster = "Nova Sonic" if nova_time < polly_time else "Polly"
        print(f"   Winner: {faster}")


async def main():
    """Run all demos"""
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║     Nova Sonic Voice Agent Demo                           ║")
    print("║     Voice-based Order Automation System                   ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Check AWS credentials
    if not os.getenv("AWS_ACCESS_KEY_ID") and not os.getenv("AWS_PROFILE"):
        print("\n⚠️  Warning: AWS credentials not found!")
        print("   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        print("   or configure AWS_PROFILE\n")
    
    try:
        # Run demos
        await demo_nova_sonic()
        await demo_polly_fallback()
        await compare_providers()
        
        print("\n" + "="*60)
        print("✅ Demo completed successfully!")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())
