#!/usr/bin/env python3
"""
Voice Service - AWS Nova Sonic & Polly Integration
Handles speech-to-text, text-to-speech, and conversational order creation
Supports both Nova Sonic (streaming audio) and Polly (fallback)
"""

import os
import json
import logging
import asyncio
import uuid
import subprocess
import tempfile
from typing import Dict, Any, Optional, List, AsyncIterator
from datetime import datetime, timezone
import base64
import io
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError
    try:
        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
        from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
        from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
        # from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver
        from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
        BIDIRECTIONAL_STREAMING_AVAILABLE = True
    except ImportError:
        BIDIRECTIONAL_STREAMING_AVAILABLE = False
        logger.warning("Bidirectional streaming SDK not available, falling back to standard converse API")
except ImportError:
    print("Warning: boto3 not installed")
    boto3 = None
    BIDIRECTIONAL_STREAMING_AVAILABLE = False


class VoiceService:
    """
    Voice Service for Nova Sonic & Polly Integration
    Handles speech-to-speech conversation for order automation
    
    Supports two modes:
    1. Nova Sonic: Direct audio-to-audio streaming with Bedrock converse_stream
    2. Polly: Traditional TTS with separate transcription (fallback)
    """

    def __init__(
        self,
        region: str = "us-west-2",
        voice_provider: str = "nova_sonic",
        voice_model: str = "amazon.nova-sonic-v1:0",
        voice_config: Optional[Dict[str, Any]] = None
    ):
        self.region = region
        self.voice_provider = voice_provider  # "nova_sonic" or "polly"
        self.voice_model = voice_model
        self.voice_config = voice_config or {
            "input_sample_rate": 16000,
            "output_sample_rate": 24000,
            "output_format": "lpcm",
            "sample_size_bits": 16,
            "channel_count": 1,
            "voice_id": "matthew",
            "encoding": "base64",
            "language": "en-US",
            "polly_voice_id": "Joanna",
            "polly_engine": "neural"
        }
        
        self.bedrock_runtime = None
        self.bedrock_streaming_client = None
        self.polly_client = None
        self.transcribe_client = None
        
        # Conversation state management
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        # Active bidirectional streams
        self.active_streams: Dict[str, Any] = {}
        
        if boto3:
            try:
                # Standard bedrock runtime for fallback
                self.bedrock_runtime = boto3.client(
                    service_name='bedrock-runtime',
                    region_name=region
                )
                
                # Initialize bidirectional streaming client if available
                if BIDIRECTIONAL_STREAMING_AVAILABLE and self.voice_provider == "nova_sonic":
                    config = Config(
                        endpoint_uri=f"https://bedrock-runtime.{region}.amazonaws.com",
                        region=region,
                        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
                        auth_scheme_resolver=HTTPAuthSchemeResolver(),
                        auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")}
                    )
                    self.bedrock_streaming_client = BedrockRuntimeClient(config=config)
                
                if self.voice_provider == "polly":
                    self.polly_client = boto3.client('polly', region_name=region)
                    self.transcribe_client = boto3.client('transcribe', region_name=region)
                
                logger.info(f"VoiceService initialized with provider: {voice_provider}, region: {region}, streaming: {BIDIRECTIONAL_STREAMING_AVAILABLE}")
            except Exception as e:
                logger.error(f"Failed to initialize AWS clients: {e}")

    async def start_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Start a new voice conversation session"""
        
        self.active_conversations[conversation_id] = {
            "id": conversation_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "state": "greeting",
            "order_data": {},
            "conversation_history": [],
            "current_field": None
        }
        
        greeting_text = """Hello! I'm your order automation assistant. 
        I can help you create orders through voice commands. 
        What product would you like to order today?"""
        
        # Generate speech from text
        audio_response = await self.text_to_speech(greeting_text)
        
        self.active_conversations[conversation_id]["conversation_history"].append({
            "role": "assistant",
            "text": greeting_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "conversation_id": conversation_id,
            "audio": audio_response,
            "text": greeting_text,
            "state": "greeting"
        }

    async def _convert_audio_to_pcm(self, audio_data: bytes, source_format: str = "webm") -> bytes:
        """
        Convert audio from various formats (webm, mp3, etc.) to PCM format
        Uses ffmpeg for conversion
        """
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix=f".{source_format}", delete=False) as input_file:
                input_path = input_file.name
                input_file.write(audio_data)

            with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as output_file:
                output_path = output_file.name

            try:
                # Convert using ffmpeg
                # -f s16le: 16-bit signed little-endian PCM
                # -ar 16000: 16kHz sample rate (required for Nova Sonic input)
                # -ac 1: mono audio
                process = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-y',
                    '-i', input_path,
                    '-f', 's16le',
                    '-ar', '16000',
                    '-ac', '1',
                    output_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
                    raise Exception("Audio conversion failed")

                # Read converted PCM data
                with open(output_path, 'rb') as f:
                    pcm_data = f.read()

                logger.info(f"Converted {len(audio_data)} bytes of {source_format} to {len(pcm_data)} bytes of PCM")
                return pcm_data

            finally:
                # Cleanup temp files
                try:
                    os.unlink(input_path)
                    os.unlink(output_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            # Fallback: return original data
            return audio_data

    async def process_speech(
        self,
        conversation_id: str,
        audio_data: bytes
    ) -> Dict[str, Any]:
        """
        Process incoming speech audio
        Routes to Nova Sonic or Polly based on configuration
        """

        # Convert audio to PCM format for Nova Sonic
        if self.voice_provider == "nova_sonic":
            # Convert WebM/other formats to PCM
            audio_data = await self._convert_audio_to_pcm(audio_data, source_format="webm")
            return await self._process_speech_nova_sonic(conversation_id, audio_data)
        else:
            return await self._process_speech_polly(conversation_id, audio_data)

    async def _process_speech_nova_sonic(
        self, 
        conversation_id: str, 
        audio_data: bytes
    ) -> Dict[str, Any]:
        """
        Process speech using Nova Sonic bidirectional streaming API
        Direct audio-to-audio conversation with Bedrock
        """
        
        if conversation_id not in self.active_conversations:
            await self.start_conversation(conversation_id)
        
        conversation = self.active_conversations[conversation_id]
        
        try:
            # Check if we should use bidirectional streaming
            if BIDIRECTIONAL_STREAMING_AVAILABLE and self.bedrock_streaming_client:
                return await self._process_speech_bidirectional(conversation_id, audio_data)
            else:
                # Fallback to converse_stream API
                return await self._process_speech_converse_stream(conversation_id, audio_data)
            
        except Exception as e:
            logger.error(f"Nova Sonic processing failed: {e}")
            raise

    async def _process_speech_bidirectional(
        self,
        conversation_id: str,
        audio_data: bytes
    ) -> Dict[str, Any]:
        """
        Process speech using bidirectional streaming API (recommended approach)
        """
        conversation = self.active_conversations[conversation_id]
        
        # Initialize stream if not exists
        if conversation_id not in self.active_streams:
            await self._initialize_bidirectional_stream(conversation_id)
        
        stream_state = self.active_streams[conversation_id]
        stream = stream_state["stream"]
        prompt_name = stream_state["prompt_name"]
        audio_content_name = stream_state["audio_content_name"]
        
        # Start audio input
        await self._send_event(stream, {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": self.voice_config["input_sample_rate"],
                        "sampleSizeBits": self.voice_config["sample_size_bits"],
                        "channelCount": self.voice_config["channel_count"],
                        "audioType": "SPEECH",
                        "encoding": self.voice_config["encoding"]
                    }
                }
            }
        })
        
        # Send audio data
        blob = base64.b64encode(audio_data)
        await self._send_event(stream, {
            "event": {
                "audioInput": {
                    "promptName": prompt_name,
                    "contentName": audio_content_name,
                    "content": blob.decode('utf-8')
                }
            }
        })
        
        # End audio input
        await self._send_event(stream, {
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": audio_content_name
                }
            }
        })
        
        # Process response
        audio_chunks = []
        text_response = ""
        user_text = ""
        current_role = None

        # Collect responses from stream - LOOP through ALL events
        try:
            output = await stream.await_output()
            output_stream = output[1]

            # Read all events from the stream
            while True:
                try:
                    result = await asyncio.wait_for(output_stream.receive(), timeout=10.0)

                    if result.value and result.value.bytes_:
                        response_data = result.value.bytes_.decode('utf-8')
                        json_data = json.loads(response_data)

                        if 'event' in json_data:
                            # Handle content start
                            if 'contentStart' in json_data['event']:
                                current_role = json_data['event']['contentStart'].get('role')
                                logger.info(f"Content start - role: {current_role}")

                            # Handle text output (transcription)
                            if 'textOutput' in json_data['event']:
                                text = json_data['event']['textOutput']['content']
                                if current_role == "USER":
                                    user_text += text
                                elif current_role == "ASSISTANT":
                                    text_response += text
                                logger.info(f"Text output ({current_role}): {text}")

                            # Handle audio output
                            if 'audioOutput' in json_data['event']:
                                audio_content = json_data['event']['audioOutput']['content']
                                audio_bytes = base64.b64decode(audio_content)
                                audio_chunks.append(audio_bytes)
                                logger.info(f"Audio chunk received: {len(audio_bytes)} bytes")

                            # Check for session end or prompt end
                            if 'promptEnd' in json_data['event'] or 'sessionEnd' in json_data['event']:
                                logger.info("Stream ended normally")
                                break

                except asyncio.TimeoutError:
                    logger.info("Stream read timeout - assuming end of response")
                    break
                except Exception as e:
                    logger.warning(f"Error reading from stream: {e}")
                    break

        except Exception as e:
            logger.error(f"Error processing stream output: {e}")
        
        # Combine audio chunks
        complete_audio = b''.join(audio_chunks)
        audio_base64 = base64.b64encode(complete_audio).decode('utf-8') if complete_audio else ""

        # Log what we got
        logger.info(f"Bidirectional stream results:")
        logger.info(f"  User text: {user_text or '[Audio input]'}")
        logger.info(f"  Assistant text: {text_response or '[EMPTY]'}")
        logger.info(f"  Audio chunks: {len(audio_chunks)}, Total bytes: {len(complete_audio)}")

        # If we didn't get a text response, provide a fallback
        if not text_response:
            text_response = "I heard your input. Could you please repeat that?"
            logger.warning("No assistant text received from Nova Sonic, using fallback")

        # Update conversation history
        conversation["conversation_history"].append({
            "role": "user",
            "text": user_text or "[Audio input]",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        conversation["conversation_history"].append({
            "role": "assistant",
            "text": text_response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Parse response for order data updates
        parsed_data = self._extract_order_data(text_response, conversation["order_data"])
        conversation["order_data"] = parsed_data["order_data"]
        conversation["state"] = parsed_data["state"]

        return {
            "conversation_id": conversation_id,
            "user_text": user_text or "[Audio input]",
            "assistant_text": text_response,
            "audio": audio_base64,
            "audio_format": self.voice_config["output_format"],
            "sample_rate": self.voice_config["output_sample_rate"],
            "state": parsed_data["state"],
            "order_data": conversation.get("order_data", {}),
            "ready_to_submit": parsed_data.get("ready_to_submit", False),
            "provider": "nova_sonic_bidirectional"
        }

    async def _initialize_bidirectional_stream(self, conversation_id: str):
        """Initialize bidirectional streaming session"""
        
        prompt_name = str(uuid.uuid4())
        content_name = str(uuid.uuid4())
        audio_content_name = str(uuid.uuid4())
        
        # Initialize the stream
        stream = await self.bedrock_streaming_client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.voice_model)
        )
        
        # Send session start event
        await self._send_event(stream, {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7
                    }
                }
            }
        })
        
        # Send prompt start event
        await self._send_event(stream, {
            "event": {
                "promptStart": {
                    "promptName": prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": self.voice_config["output_sample_rate"],
                        "sampleSizeBits": self.voice_config["sample_size_bits"],
                        "channelCount": self.voice_config["channel_count"],
                        "voiceId": self.voice_config["voice_id"],
                        "encoding": self.voice_config["encoding"],
                        "audioType": "SPEECH"
                    }
                }
            }
        })
        
        # Send system prompt
        conversation = self.active_conversations[conversation_id]
        system_prompt = self._get_order_collection_system_prompt(
            conversation.get("order_data", {})
        )
        
        await self._send_event(stream, {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "SYSTEM",
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        })
        
        await self._send_event(stream, {
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": system_prompt
                }
            }
        })
        
        await self._send_event(stream, {
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": content_name
                }
            }
        })
        
        # Store stream state
        self.active_streams[conversation_id] = {
            "stream": stream,
            "prompt_name": prompt_name,
            "content_name": content_name,
            "audio_content_name": audio_content_name,
            "is_active": True
        }

    async def _send_event(self, stream, event_dict: Dict[str, Any]):
        """Send an event to the bidirectional stream"""
        event_json = json.dumps(event_dict)
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        await stream.input_stream.send(event)

    async def _process_speech_converse_stream(
        self, 
        conversation_id: str, 
        audio_data: bytes
    ) -> Dict[str, Any]:
        """
        Fallback: Process speech using converse_stream API (legacy approach)
        """
        
        conversation = self.active_conversations[conversation_id]
        
        try:
            # Build conversation messages
            messages = self._build_conversation_messages(conversation)
            
            # Add user audio input
            messages.append({
                "role": "user",
                "content": [
                    {
                        "audio": {
                            "format": "pcm",
                            "source": {
                                "bytes": audio_data
                            }
                        }
                    }
                ]
            })
            
            # System prompt for order collection
            system_prompt = self._get_order_collection_system_prompt(
                conversation.get("order_data", {})
            )
            
            # Call Nova Sonic with streaming
            response = self.bedrock_runtime.converse_stream(
                modelId=self.voice_model,
                messages=messages,
                system=[{"text": system_prompt}],
                inferenceConfig={
                    "maxTokens": 1000,
                    "temperature": 0.7
                },
                additionalModelRequestFields={
                    "audio": {
                        "output": {
                            "sampleRate": self.voice_config["output_sample_rate"],
                            "format": self.voice_config["output_format"]
                        }
                    }
                }
            )
            
            # Process streaming response
            audio_chunks = []
            text_response = ""
            
            stream = response.get('stream')
            if stream:
                for event in stream:
                    if 'contentBlockDelta' in event:
                        delta = event['contentBlockDelta']['delta']
                        
                        # Collect text transcript
                        if 'text' in delta:
                            text_response += delta['text']
                        
                        # Collect audio chunks
                        if 'audio' in delta:
                            audio_bytes = delta['audio'].get('bytes')
                            if audio_bytes:
                                audio_chunks.append(audio_bytes)
            
            # Combine audio chunks
            complete_audio = b''.join(audio_chunks)
            audio_base64 = base64.b64encode(complete_audio).decode('utf-8')
            
            # Update conversation history
            conversation["conversation_history"].append({
                "role": "user",
                "text": "[Audio input]",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            conversation["conversation_history"].append({
                "role": "assistant",
                "text": text_response,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Parse response for order data updates
            parsed_data = self._extract_order_data(text_response, conversation["order_data"])
            conversation["order_data"] = parsed_data["order_data"]
            conversation["state"] = parsed_data["state"]
            
            return {
                "conversation_id": conversation_id,
                "user_text": "[Audio input]",
                "assistant_text": text_response,
                "audio": audio_base64,
                "audio_format": self.voice_config["output_format"],
                "sample_rate": self.voice_config["output_sample_rate"],
                "state": parsed_data["state"],
                "order_data": conversation.get("order_data", {}),
                "ready_to_submit": parsed_data.get("ready_to_submit", False),
                "provider": "nova_sonic"
            }
            
        except Exception as e:
            logger.error(f"Nova Sonic processing failed: {e}")
            raise

    async def _process_speech_polly(
        self, 
        conversation_id: str, 
        audio_data: bytes
    ) -> Dict[str, Any]:
        """
        Process speech using traditional Polly + Transcribe approach
        1. Convert speech to text
        2. Process with conversational AI
        3. Generate speech response
        """
        
        if conversation_id not in self.active_conversations:
            await self.start_conversation(conversation_id)
        
        conversation = self.active_conversations[conversation_id]
        
        # Step 1: Speech to Text
        user_text = await self.speech_to_text(audio_data)
        
        # Add to conversation history
        conversation["conversation_history"].append({
            "role": "user",
            "text": user_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Step 2: Process with conversational AI
        ai_response = await self.process_conversation(conversation_id, user_text)
        
        # Step 3: Text to Speech using Polly
        audio_response = await self.text_to_speech_polly(ai_response["text"])
        
        # Add to conversation history
        conversation["conversation_history"].append({
            "role": "assistant",
            "text": ai_response["text"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "conversation_id": conversation_id,
            "user_text": user_text,
            "assistant_text": ai_response["text"],
            "audio": audio_response,
            "audio_format": "mp3",
            "state": ai_response["state"],
            "order_data": conversation.get("order_data", {}),
            "ready_to_submit": ai_response.get("ready_to_submit", False),
            "provider": "polly"
        }

    def _build_conversation_messages(self, conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build message history for Nova Sonic API"""
        messages = []
        
        # Get recent conversation history (last 10 exchanges)
        history = conversation.get("conversation_history", [])[-10:]
        
        for msg in history:
            if msg["role"] in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["text"]}]
                })
        
        return messages

    def _get_order_collection_system_prompt(self, order_data: Dict[str, Any]) -> str:
        """Generate system prompt for order collection"""

        # Determine what's still needed
        required_fields = {
            "product_name": "Product name",
            "quantity": "Quantity (how many items)",
            "customer_name": "Customer full name",
            "customer_email": "Email address",
            "phone": "Phone number",
            "street": "Street address",
            "city": "City",
            "state": "State (2-letter code)",
            "postal_code": "ZIP/postal code"
        }

        collected = [k for k in required_fields.keys() if k in order_data and order_data[k]]
        missing = [v for k, v in required_fields.items() if k not in order_data or not order_data[k]]

        return f"""You are a helpful voice assistant for automated order placement.
Your task is to collect order information through natural conversation.

REQUIRED INFORMATION TO COLLECT:
1. Product Details:
   - product_name: Name/description of the product
   - quantity: How many items (ask explicitly, don't assume)
   - size: Size/variant (optional, ask if applicable like clothing/shoes)
   - color: Color/variant (optional, ask if applicable)
   - product_url: URL (optional, say you can search if not provided)

CURRENT PROGRESS:
Collected: {', '.join(collected) if collected else 'Nothing yet'}
Still needed: {', '.join(missing) if missing else 'All required fields collected!'}

Current data: {json.dumps(order_data, indent=2)}

CONVERSATION GUIDELINES:
1. Be warm, friendly, and conversational
2. Ask for ONE thing at a time - don't overwhelm
3. If user provides multiple items at once, acknowledge all and continue
4. Validate critical info (email should have @, phone should be numbers, zip should be 5 digits)
5. After collecting product, ask about quantity explicitly
6. For address, collect in order: street → city → state → zip
7. When ALL fields collected, provide complete summary and ask for confirmation
8. Keep responses concise for voice - 1-2 sentences max per response

CONFIRMATION FORMAT (when all data collected):
"Let me confirm your order:
- Product: [name], size [X], color [Y], quantity [N]

Should I submit this order for processing?"

Your responses must be natural spoken language, not JSON or structured format."""

    def _extract_order_data(self, text: str, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and update order data from assistant response
        This is a simple implementation - could be enhanced with NER or structured output
        """

        # Simple keyword-based extraction (could be improved with LLM-based extraction)
        updated_data = current_data.copy()

        # Determine state based on what's collected
        required_fields = [
            "product_name",
            "quantity"
        ]

        collected_fields = [f for f in required_fields if f in updated_data and updated_data[f]]
        missing_fields = [f for f in required_fields if f not in updated_data or not updated_data[f]]

        # Determine conversation state
        if len(collected_fields) == 0:
            state = "greeting"
        elif len(collected_fields) < 3:
            state = "collecting_product"
        elif "product_name" in collected_fields and "quantity" in collected_fields and not all(f in collected_fields for f in ["customer_name", "customer_email", "phone"]):
            state = "collecting_customer"
        elif all(f in collected_fields for f in ["customer_name", "customer_email", "phone"]) and not all(f in collected_fields for f in ["street", "city", "state", "postal_code"]):
            state = "collecting_address"
        elif len(missing_fields) > 0:
            state = "collecting"
        else:
            state = "confirming"

        # Check if user confirmed and all data is collected
        confirmation_keywords = ["yes", "confirm", "correct", "place order", "submit", "go ahead", "proceed"]
        ready_to_submit = (
            len(missing_fields) == 0 and
            state == "confirming" and
            any(keyword in text.lower() for keyword in confirmation_keywords)
        )

        logger.info(f"Data extraction: {len(collected_fields)}/{len(required_fields)} fields collected")
        logger.info(f"State: {state}, Ready: {ready_to_submit}")
        if missing_fields:
            logger.info(f"Missing fields: {missing_fields}")

        return {
            "order_data": updated_data,
            "state": state,
            "ready_to_submit": ready_to_submit,
            "collected_fields": collected_fields,
            "missing_fields": missing_fields
        }

    async def speech_to_text(self, audio_data: bytes) -> str:
        """
        Convert speech audio to text using Amazon Transcribe
        """
        try:
            # Use Amazon Transcribe for speech-to-text
            transcribe = boto3.client('transcribe', region_name=self.region)
            
            # For real-time transcription, use TranscribeStreaming
            # This is a simplified version - actual implementation would use streaming API
            
            # For now, return placeholder - integrate with actual Transcribe API
            logger.info("Processing speech-to-text conversion")
            
            # Actual implementation would use:
            # transcribe_streaming = boto3.client('transcribe-streaming')
            # Use start_stream_transcription for real-time conversion
            
            return "Product order request"  # Placeholder
            
        except Exception as e:
            logger.error(f"Speech-to-text conversion failed: {e}")
            raise

    async def text_to_speech(self, text: str) -> str:
        """
        Convert text to speech - routes to appropriate provider
        Returns base64 encoded audio
        """
        if self.voice_provider == "nova_sonic":
            return await self.text_to_speech_nova_sonic(text)
        else:
            return await self.text_to_speech_polly(text)

    async def text_to_speech_nova_sonic(self, text: str) -> str:
        """
        Convert text to speech using Nova Sonic
        Returns base64 encoded audio
        """
        try:
            # Use bidirectional streaming if available
            if BIDIRECTIONAL_STREAMING_AVAILABLE and self.bedrock_streaming_client:
                return await self._text_to_speech_bidirectional(text)
            else:
                # Fallback to converse_stream
                return await self._text_to_speech_converse_stream(text)
            
        except Exception as e:
            logger.error(f"Nova Sonic TTS failed: {e}")
            raise

    async def _text_to_speech_bidirectional(self, text: str) -> str:
        """Convert text to speech using bidirectional streaming API"""
        
        prompt_name = str(uuid.uuid4())
        content_name = str(uuid.uuid4())
        
        # Initialize the stream
        stream = await self.bedrock_streaming_client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.voice_model)
        )
        
        # Send session start
        await self._send_event(stream, {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 500,
                        "topP": 0.9,
                        "temperature": 0.7
                    }
                }
            }
        })
        
        # Send prompt start
        await self._send_event(stream, {
            "event": {
                "promptStart": {
                    "promptName": prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": self.voice_config["output_sample_rate"],
                        "sampleSizeBits": self.voice_config["sample_size_bits"],
                        "channelCount": self.voice_config["channel_count"],
                        "voiceId": self.voice_config["voice_id"],
                        "encoding": self.voice_config["encoding"],
                        "audioType": "SPEECH"
                    }
                }
            }
        })
        
        # Send text content
        await self._send_event(stream, {
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "USER",
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        })
        
        await self._send_event(stream, {
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": text
                }
            }
        })
        
        await self._send_event(stream, {
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": content_name
                }
            }
        })
        
        # End prompt
        await self._send_event(stream, {
            "event": {
                "promptEnd": {
                    "promptName": prompt_name
                }
            }
        })
        
        # End session
        await self._send_event(stream, {
            "event": {
                "sessionEnd": {}
            }
        })
        
        # Collect audio response
        audio_chunks = []
        try:
            output = await stream.await_output()
            output_stream = output[1]

            while True:
                try:
                    result = await asyncio.wait_for(output_stream.receive(), timeout=10.0)

                    if result.value and result.value.bytes_:
                        response_data = result.value.bytes_.decode('utf-8')
                        json_data = json.loads(response_data)

                        if 'event' in json_data:
                            if 'audioOutput' in json_data['event']:
                                audio_content = json_data['event']['audioOutput']['content']
                                audio_bytes = base64.b64decode(audio_content)
                                audio_chunks.append(audio_bytes)
                                logger.info(f"TTS audio chunk: {len(audio_bytes)} bytes")

                            # Check for end of stream
                            if 'sessionEnd' in json_data['event']:
                                logger.info("TTS session ended")
                                break

                except asyncio.TimeoutError:
                    logger.info("TTS stream timeout - response complete")
                    break
                except Exception as e:
                    logger.warning(f"TTS stream read error: {e}")
                    break
        except Exception as e:
            logger.error(f"TTS stream error: {e}")
        
        # Close stream
        await stream.input_stream.close()
        
        # Combine and encode
        complete_audio = b''.join(audio_chunks)
        audio_base64 = base64.b64encode(complete_audio).decode('utf-8')
        
        return audio_base64

    async def _text_to_speech_converse_stream(self, text: str) -> str:
        """Fallback: Convert text to speech using converse_stream API"""
        
        response = self.bedrock_runtime.converse_stream(
            modelId=self.voice_model,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": text}]
                }
            ],
            system=[{"text": "You are a voice assistant. Repeat the user's message naturally."}],
            inferenceConfig={
                "maxTokens": 500,
                "temperature": 0.7
            },
            additionalModelRequestFields={
                "audio": {
                    "output": {
                        "sampleRate": self.voice_config["output_sample_rate"],
                        "format": self.voice_config["output_format"]
                    }
                }
            }
        )
        
        # Collect audio chunks from stream
        audio_chunks = []
        stream = response.get('stream')
        if stream:
            for event in stream:
                if 'contentBlockDelta' in event:
                    delta = event['contentBlockDelta']['delta']
                    if 'audio' in delta:
                        audio_bytes = delta['audio'].get('bytes')
                        if audio_bytes:
                            audio_chunks.append(audio_bytes)
        
        # Combine and encode
        complete_audio = b''.join(audio_chunks)
        audio_base64 = base64.b64encode(complete_audio).decode('utf-8')
        
        return audio_base64

    async def text_to_speech_polly(self, text: str) -> str:
        """
        Convert text to speech using Amazon Polly with Neural voices
        Returns base64 encoded audio
        """
        try:
            if not self.polly_client:
                self.polly_client = boto3.client('polly', region_name=self.region)
            
            response = self.polly_client.synthesize_speech(
                Text=text,
                OutputFormat='mp3',
                VoiceId=self.voice_config.get("polly_voice_id", "Joanna"),
                Engine=self.voice_config.get("polly_engine", "neural"),
                LanguageCode=self.voice_config.get("language", "en-US")
            )
            
            # Read audio stream
            audio_stream = response['AudioStream'].read()
            
            # Encode to base64 for transmission
            audio_base64 = base64.b64encode(audio_stream).decode('utf-8')
            
            return audio_base64
            
        except Exception as e:
            logger.error(f"Polly TTS failed: {e}")
            raise

    async def process_conversation(
        self, 
        conversation_id: str, 
        user_input: str
    ) -> Dict[str, Any]:
        """
        Process conversational flow for order creation
        Uses Amazon Bedrock with Claude for natural language understanding
        """
        
        conversation = self.active_conversations[conversation_id]
        order_data = conversation["order_data"]
        current_state = conversation["state"]
        
        # Build conversation context
        conversation_history = conversation["conversation_history"]
        
        # Create prompt for Claude
        prompt = self._build_conversation_prompt(
            conversation_history, 
            user_input, 
            order_data, 
            current_state
        )
        
        # Call Bedrock with Claude
        try:
            response = self.bedrock_runtime.converse(
                modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": 500,
                    "temperature": 0.7
                }
            )
            
            assistant_message = response['output']['message']['content'][0]['text']
            
            # Parse response to extract order data and next state
            parsed_response = self._parse_assistant_response(
                assistant_message, 
                order_data
            )
            
            # Update conversation state
            conversation["order_data"] = parsed_response["order_data"]
            conversation["state"] = parsed_response["next_state"]
            conversation["current_field"] = parsed_response.get("current_field")
            
            return {
                "text": parsed_response["response_text"],
                "state": parsed_response["next_state"],
                "ready_to_submit": parsed_response.get("ready_to_submit", False)
            }
            
        except Exception as e:
            logger.error(f"Conversation processing failed: {e}")
            return {
                "text": "I'm sorry, I had trouble understanding that. Could you please repeat?",
                "state": current_state,
                "ready_to_submit": False
            }

    def _build_conversation_prompt(
        self, 
        history: List[Dict], 
        user_input: str,
        order_data: Dict,
        current_state: str
    ) -> str:
        """Build prompt for conversational AI"""
        
        prompt = f"""You are a helpful order automation assistant having a natural conversation with a user to collect order information.

Current conversation state: {current_state}
Order data collected so far: {json.dumps(order_data, indent=2)}

Required order fields:
- product_name: Name of the product

Conversation history:
"""
        
        for msg in history[-6:]:  # Last 6 messages for context
            prompt += f"{msg['role']}: {msg['text']}\n"
        
        prompt += f"\nUser: {user_input}\n\n"
        
        prompt += """Instructions:
1. Have a natural, friendly conversation
2. Ask for one piece of information at a time
3. Validate and confirm important details
4. When you have all required information, ask for final confirmation
5. Respond in a conversational tone

Your response should include:
- Natural conversational reply to the user
- Update any order_data fields based on user's response
- Indicate next_state (greeting, collecting_product, collecting_customer, collecting_shipping, confirming, ready)
- If all information collected and confirmed, set ready_to_submit: true

Format your response as JSON:
{
  "response_text": "Your natural language response",
  "order_data": {updated order data},
  "next_state": "state_name",
  "current_field": "field being collected",
  "ready_to_submit": false
}
"""
        
        return prompt

    def _parse_assistant_response(
        self, 
        assistant_message: str, 
        current_order_data: Dict
    ) -> Dict[str, Any]:
        """Parse AI response and extract structured data"""
        
        try:
            # Try to parse as JSON
            if assistant_message.strip().startswith('{'):
                parsed = json.loads(assistant_message)
                
                # Merge order data
                merged_order_data = {**current_order_data, **parsed.get("order_data", {})}
                
                return {
                    "response_text": parsed.get("response_text", ""),
                    "order_data": merged_order_data,
                    "next_state": parsed.get("next_state", "collecting"),
                    "current_field": parsed.get("current_field"),
                    "ready_to_submit": parsed.get("ready_to_submit", False)
                }
            else:
                # Fallback: treat as plain text response
                return {
                    "response_text": assistant_message,
                    "order_data": current_order_data,
                    "next_state": "collecting",
                    "ready_to_submit": False
                }
                
        except json.JSONDecodeError:
            logger.warning("Failed to parse assistant response as JSON")
            return {
                "response_text": assistant_message,
                "order_data": current_order_data,
                "next_state": "collecting",
                "ready_to_submit": False
            }

    def get_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of a conversation"""
        return self.active_conversations.get(conversation_id)

    def end_conversation(self, conversation_id: str) -> None:
        """End and cleanup conversation"""
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
            logger.info(f"Conversation {conversation_id} ended")
        
        # Cleanup bidirectional stream if exists
        if conversation_id in self.active_streams:
            asyncio.create_task(self._cleanup_stream(conversation_id))

    async def _cleanup_stream(self, conversation_id: str):
        """Cleanup bidirectional streaming session"""
        if conversation_id not in self.active_streams:
            return
        
        stream_state = self.active_streams[conversation_id]
        stream = stream_state["stream"]
        prompt_name = stream_state["prompt_name"]
        
        try:
            # Send prompt end
            await self._send_event(stream, {
                "event": {
                    "promptEnd": {
                        "promptName": prompt_name
                    }
                }
            })
            
            # Send session end
            await self._send_event(stream, {
                "event": {
                    "sessionEnd": {}
                }
            })
            
            # Close stream
            await stream.input_stream.close()
            
        except Exception as e:
            logger.warning(f"Error cleaning up stream: {e}")
        finally:
            del self.active_streams[conversation_id]

    async def get_order_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Get summary of collected order data"""
        
        if conversation_id not in self.active_conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        conversation = self.active_conversations[conversation_id]
        order_data = conversation["order_data"]
        
        # Generate summary speech
        summary_text = f"""Let me confirm your order:
        Product: {order_data.get('product_name', 'Not specified')}
        
        Would you like to proceed with this order?
        """
        
        audio_response = await self.text_to_speech(summary_text)
        
        return {
            "text": summary_text,
            "audio": audio_response,
            "order_data": order_data,
            "ready_to_submit": True
        }


# Singleton instance
_voice_service_instance = None


def get_voice_service(
    region: str = "us-east-1",
    voice_provider: Optional[str] = None,
    voice_model: Optional[str] = None,
    voice_config: Optional[Dict[str, Any]] = None,
    config_manager=None
) -> VoiceService:
    """
    Get or create VoiceService singleton
    
    Args:
        region: AWS region
        voice_provider: "nova_sonic" or "polly" (default from config)
        voice_model: Model ID for Nova Sonic
        voice_config: Voice configuration dict
        config_manager: ConfigManager instance for loading settings
    """
    global _voice_service_instance
    
    # Load from config manager if available
    if config_manager:
        system_config = config_manager.get_system_config()
        region = system_config.get("voice_region", os.getenv("NOVA_SONIC_REGION", os.getenv("AWS_REGION", "us-west-2")))
        voice_provider = voice_provider or system_config.get("voice_provider", "polly")
        voice_model = voice_model or system_config.get("voice_model", "amazon.nova-sonic-v1:0")
        voice_config = voice_config or system_config.get("voice_config", {})
    else:
        # Use defaults from environment
        region = os.getenv("NOVA_SONIC_REGION", os.getenv("AWS_REGION", "us-west-2"))
        voice_provider = voice_provider or os.getenv("VOICE_PROVIDER", "polly")
        voice_model = voice_model or os.getenv("VOICE_MODEL", "amazon.nova-sonic-v1:0")
        voice_config = voice_config or {}

    if _voice_service_instance is None:
        _voice_service_instance = VoiceService(
            region=region,
            voice_provider=voice_provider,
            voice_model=voice_model,
            voice_config=voice_config
        )
    
    return _voice_service_instance
