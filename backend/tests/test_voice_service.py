#!/usr/bin/env python3
"""
Test suite for Nova Sonic Voice Service
Tests both Nova Sonic and Polly providers
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestVoiceService(unittest.TestCase):
    """Test VoiceService class"""
    
    def setUp(self):
        """Set up test fixtures"""
        from services.voice_service import VoiceService
        
        self.nova_service = VoiceService(
            region="us-west-2",
            voice_provider="nova_sonic",
            voice_model="us.amazon.nova-sonic-v1:0"
        )
        
        self.polly_service = VoiceService(
            region="us-west-2",
            voice_provider="polly"
        )
    
    def test_initialization_nova_sonic(self):
        """Test Nova Sonic initialization"""
        self.assertEqual(self.nova_service.voice_provider, "nova_sonic")
        self.assertEqual(self.nova_service.voice_model, "us.amazon.nova-sonic-v1:0")
        self.assertIsNotNone(self.nova_service.bedrock_runtime)
    
    def test_initialization_polly(self):
        """Test Polly initialization"""
        self.assertEqual(self.polly_service.voice_provider, "polly")
        self.assertIsNotNone(self.polly_service.voice_config)
        self.assertEqual(
            self.polly_service.voice_config.get("polly_voice_id"),
            "Joanna"
        )
    
    def test_conversation_state_management(self):
        """Test conversation state management"""
        conv_id = "test-conv-123"
        
        # Initially no conversation
        self.assertIsNone(self.nova_service.get_conversation_state(conv_id))
        
        # Create conversation (sync wrapper)
        asyncio.run(self.nova_service.start_conversation(conv_id))
        
        # Conversation should exist
        state = self.nova_service.get_conversation_state(conv_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["id"], conv_id)
        self.assertEqual(state["state"], "greeting")
        
        # End conversation
        self.nova_service.end_conversation(conv_id)
        
        # Should be gone
        self.assertIsNone(self.nova_service.get_conversation_state(conv_id))
    
    def test_build_conversation_messages(self):
        """Test conversation message building"""
        conversation = {
            "conversation_history": [
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Hi there!"},
                {"role": "user", "text": "I need help"}
            ]
        }
        
        messages = self.nova_service._build_conversation_messages(conversation)
        
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")
    
    def test_order_data_extraction(self):
        """Test order data extraction from text"""
        current_data = {"product_name": "Laptop"}
        text_response = "Great choice! Now I need your email address."
        
        result = self.nova_service._extract_order_data(text_response, current_data)
        
        self.assertIn("order_data", result)
        self.assertIn("state", result)
        self.assertIn("ready_to_submit", result)
        self.assertEqual(result["order_data"]["product_name"], "Laptop")
    
    def test_system_prompt_generation(self):
        """Test system prompt generation"""
        order_data = {
            "product_name": "Laptop",
            "customer_name": "John Doe"
        }
        
        prompt = self.nova_service._get_order_collection_system_prompt(order_data)
        
        self.assertIn("order information", prompt.lower())
        self.assertIn("product_name", prompt)
        self.assertIn("customer_email", prompt)
        self.assertIn("Laptop", prompt)
        self.assertIn("John Doe", prompt)


class TestVoiceServiceIntegration(unittest.TestCase):
    """Integration tests (require AWS credentials)"""
    
    @unittest.skipUnless(
        os.getenv("RUN_INTEGRATION_TESTS"),
        "Set RUN_INTEGRATION_TESTS=1 to run integration tests"
    )
    def test_nova_sonic_tts(self):
        """Test Nova Sonic text-to-speech (integration)"""
        import os
        from services.voice_service import VoiceService
        
        service = VoiceService(
            region="us-west-2",
            voice_provider="nova_sonic"
        )
        
        async def test():
            text = "This is a test."
            audio = await service.text_to_speech_nova_sonic(text)
            self.assertIsInstance(audio, str)
            self.assertTrue(len(audio) > 0)
        
        asyncio.run(test())
    
    @unittest.skipUnless(
        os.getenv("RUN_INTEGRATION_TESTS"),
        "Set RUN_INTEGRATION_TESTS=1 to run integration tests"
    )
    def test_polly_tts(self):
        """Test Polly text-to-speech (integration)"""
        import os
        from services.voice_service import VoiceService
        
        service = VoiceService(
            region="us-west-2",
            voice_provider="polly"
        )
        
        async def test():
            text = "This is a test."
            audio = await service.text_to_speech_polly(text)
            self.assertIsInstance(audio, str)
            self.assertTrue(len(audio) > 0)
        
        asyncio.run(test())


class TestConfigIntegration(unittest.TestCase):
    """Test configuration integration"""
    
    def test_config_manager_voice_settings(self):
        """Test voice settings in config manager"""
        from config import ConfigManager
        
        config_mgr = ConfigManager()
        system_config = config_mgr.get_system_config()
        
        # Should have voice settings
        self.assertIn("voice_provider", system_config)
        self.assertIn("voice_model", system_config)
        self.assertIn("voice_config", system_config)
        
        # Check defaults
        self.assertIn(system_config["voice_provider"], ["nova_sonic", "polly"])
    
    def test_get_voice_service_with_config(self):
        """Test getting voice service with config manager"""
        from services.voice_service import get_voice_service
        from config import ConfigManager
        
        config_mgr = ConfigManager()
        service = get_voice_service(config_manager=config_mgr)
        
        self.assertIsNotNone(service)
        self.assertIsNotNone(service.voice_provider)


def run_tests():
    """Run all tests"""
    import os
    
    print("=" * 70)
    print("Nova Sonic Voice Service Test Suite")
    print("=" * 70)
    
    # Check for integration tests
    if os.getenv("RUN_INTEGRATION_TESTS"):
        print("⚠️  Integration tests enabled (requires AWS credentials)")
    else:
        print("ℹ️  Integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)")
    
    print()
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 70)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import os
    sys.exit(run_tests())
