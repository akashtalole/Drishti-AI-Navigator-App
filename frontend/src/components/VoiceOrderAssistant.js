/**
 * VoiceOrderAssistant - Voice-powered order creation using AWS Nova Sonic
 * Provides speech-to-speech conversation for creating orders
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  Alert,
  ProgressBar,
  Header,
  Container,
  StatusIndicator,
  Textarea,
  ColumnLayout,
  Select,
  FormField,
  Badge
} from '@cloudscape-design/components';

const VoiceOrderAssistant = ({ visible, onDismiss, onOrderCreated }) => {
  const [conversationId, setConversationId] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [conversationState, setConversationState] = useState('idle');
  const [orderData, setOrderData] = useState({});
  const [conversationHistory, setConversationHistory] = useState([]);
  const [readyToSubmit, setReadyToSubmit] = useState(false);
  const [error, setError] = useState(null);
  const [automationMethod, setAutomationMethod] = useState('strands');
  const [collectedFields, setCollectedFields] = useState([]);
  const [missingFields, setMissingFields] = useState([]);
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const audioElementRef = useRef(null);

  // Initialize conversation when modal opens
  useEffect(() => {
    if (visible && !conversationId) {
      startConversation();
    }
  }, [visible]);

  // Cleanup when modal closes
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  const startConversation = async () => {
    try {
      setError(null);
      setIsProcessing(true);

      const response = await fetch('/api/voice/conversation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error('Failed to start conversation');
      }

      const data = await response.json();
      
      setConversationId(data.conversation_id);
      setConversationState(data.state);
      
      // Add initial greeting to history
      setConversationHistory([{
        role: 'assistant',
        text: data.text,
        timestamp: new Date().toISOString()
      }]);

      // Play greeting audio
      await playAudio(data.audio, data.audio_format || 'pcm', data.sample_rate || 24000);

      setIsProcessing(false);
    } catch (err) {
      console.error('Failed to start conversation:', err);
      setError('Failed to start voice conversation. Please try again.');
      setIsProcessing(false);
    }
  };

  const playAudio = async (base64Audio, audioFormat = 'pcm', sampleRate = 24000) => {
    try {
      // Decode base64 audio
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Handle different audio formats
      if (audioFormat === 'pcm' || audioFormat === 'lpcm') {
        // PCM/LPCM format - need to convert to playable format using Web Audio API
        await playPCMAudio(bytes, sampleRate);
      } else {
        // Standard audio formats (mp3, webm, etc.)
        const mimeType = audioFormat === 'mp3' ? 'audio/mp3' : `audio/${audioFormat}`;
        const audioBlob = new Blob([bytes], { type: mimeType });
        const audioUrl = URL.createObjectURL(audioBlob);

        // Play audio
        if (audioElementRef.current) {
          audioElementRef.current.src = audioUrl;
          await audioElementRef.current.play();
        }
      }
    } catch (err) {
      console.error('Failed to play audio:', err);
      // Don't throw - audio playback failure shouldn't break the flow
    }
  };

  const playPCMAudio = async (pcmData, sampleRate) => {
    try {
      console.log(`Playing PCM audio: ${pcmData.length} bytes at ${sampleRate}Hz`);

      // Check if we have audio data
      if (!pcmData || pcmData.length === 0) {
        console.warn('No PCM audio data to play');
        return;
      }

      // Initialize audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }

      const audioContext = audioContextRef.current;

      // Resume audio context if suspended (browser autoplay policy)
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      // Convert PCM bytes to Float32Array
      // Assuming 16-bit PCM (2 bytes per sample)
      const dataView = new DataView(pcmData.buffer);
      const samples = new Float32Array(pcmData.length / 2);

      for (let i = 0; i < samples.length; i++) {
        // Read 16-bit signed integer and convert to float (-1.0 to 1.0)
        const int16 = dataView.getInt16(i * 2, true); // true for little-endian
        samples[i] = int16 / 32768.0;
      }

      console.log(`Converted to ${samples.length} samples`);

      // Create audio buffer
      const audioBuffer = audioContext.createBuffer(1, samples.length, sampleRate);
      audioBuffer.getChannelData(0).set(samples);

      // Create source and play
      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);
      source.start(0);

      console.log(`Audio playback started (duration: ${audioBuffer.duration}s)`);

      // Wait for playback to complete
      return new Promise((resolve) => {
        source.onended = () => {
          console.log('Audio playback completed');
          resolve();
        };
      });
    } catch (err) {
      console.error('Failed to play PCM audio:', err);
      setError(`Audio playback error: ${err.message}`);
    }
  };

  const startRecording = async () => {
    try {
      setError(null);
      
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Create MediaRecorder
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await processVoiceInput(audioBlob);
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Microphone access denied. Please enable microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processVoiceInput = async (audioBlob) => {
    try {
      setIsProcessing(true);
      
      // Create form data with audio file
      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'voice_input.webm');

      const response = await fetch(
        `/api/voice/conversation/${conversationId}/process`,
        {
          method: 'POST',
          body: formData
        }
      );

      if (!response.ok) {
        throw new Error('Failed to process voice input');
      }

      const data = await response.json();
      
      // Update conversation history
      setConversationHistory(prev => [
        ...prev,
        {
          role: 'user',
          text: data.user_text,
          timestamp: new Date().toISOString()
        },
        {
          role: 'assistant',
          text: data.assistant_text,
          timestamp: new Date().toISOString()
        }
      ]);

      // Update order data and state
      setOrderData(data.order_data);
      setConversationState(data.state);
      setReadyToSubmit(data.ready_to_submit);
      setCollectedFields(data.collected_fields || []);
      setMissingFields(data.missing_fields || []);

      // Play response audio
      await playAudio(data.audio, data.audio_format || 'pcm', data.sample_rate || 24000);

      setIsProcessing(false);
    } catch (err) {
      console.error('Failed to process voice input:', err);
      setError('Failed to process your voice. Please try again.');
      setIsProcessing(false);
    }
  };

  const submitOrder = async () => {
    try {
      setIsProcessing(true);
      setError(null);

      const response = await fetch(
        `/api/voice/conversation/${conversationId}/submit?automation_method=${automationMethod}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit order');
      }

      const data = await response.json();

      console.log('Order submitted successfully:', data);

      // Notify parent component
      if (onOrderCreated) {
        onOrderCreated(data.order_id);
      }

      // Show success message
      alert(`Order ${data.order_id} created successfully! Browser automation will start shortly.`);

      // Close modal
      handleDismiss();

    } catch (err) {
      console.error('Failed to submit order:', err);
      setError(err.message || 'Failed to submit order. Please try again.');
      setIsProcessing(false);
    }
  };

  const handleDismiss = async () => {
    // End conversation on server
    if (conversationId) {
      try {
        await fetch(`/api/voice/conversation/${conversationId}`, {
          method: 'DELETE'
        });
      } catch (err) {
        console.error('Failed to end conversation:', err);
      }
    }
    
    // Reset state
    setConversationId(null);
    setConversationHistory([]);
    setOrderData({});
    setReadyToSubmit(false);
    setConversationState('idle');
    setError(null);
    
    onDismiss();
  };

  return (
    <>
      {/* Hidden audio element for playback */}
      <audio ref={audioElementRef} style={{ display: 'none' }} />
      
      <Modal
        visible={visible}
        onDismiss={handleDismiss}
        header={<Header variant="h2">🎤 Voice Order Assistant</Header>}
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={handleDismiss}>
                Cancel
              </Button>
              {readyToSubmit && (
                <Button
                  variant="primary"
                  onClick={submitOrder}
                  loading={isProcessing}
                  disabled={!readyToSubmit}
                >
                  Submit Order
                </Button>
              )}
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="l">
          {error && (
            <Alert type="error" dismissible onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Status Indicator */}
          <Container>
            <SpaceBetween size="m">
              <ColumnLayout columns={3}>
                <div>
                  <Box variant="awsui-key-label">Status</Box>
                  <StatusIndicator type={isRecording ? 'in-progress' : 'success'}>
                    {isRecording ? 'Listening...' : 
                     isProcessing ? 'Processing...' : 
                     'Ready'}
                  </StatusIndicator>
                </div>
                <div>
                  <Box variant="awsui-key-label">State</Box>
                  <div>{conversationState}</div>
                </div>
                <div>
                  <Box variant="awsui-key-label">Order Status</Box>
                  <StatusIndicator type={readyToSubmit ? 'success' : 'pending'}>
                    {readyToSubmit ? 'Ready to Submit' : 'Collecting Information'}
                  </StatusIndicator>
                </div>
              </ColumnLayout>
            </SpaceBetween>
          </Container>

          {/* Automation Method Selector */}
          <Container header={<Header variant="h3">Automation Settings</Header>}>
            <FormField label="Automation Method" description="Select how your order will be processed">
              <Select
                selectedOption={{
                  label: automationMethod === 'strands' ? 'Strands Agent (Recommended)' : 'Nova Act',
                  value: automationMethod
                }}
                onChange={({ detail }) => setAutomationMethod(detail.selectedOption.value)}
                options={[
                  {
                    label: 'Strands Agent (Recommended)',
                    value: 'strands',
                    description: 'Multi-step AI agent with error recovery'
                  },
                  {
                    label: 'Nova Act',
                    value: 'nova_act',
                    description: 'Vision-based browser automation'
                  }
                ]}
                disabled={conversationId !== null}
              />
            </FormField>
          </Container>

          {/* Recording Controls */}
          <Container header={<Header variant="h3">Voice Controls</Header>}>
            <SpaceBetween size="m">
              <Box textAlign="center">
                {!isRecording ? (
                  <Button
                    variant="primary"
                    iconName="microphone"
                    onClick={startRecording}
                    disabled={isProcessing || !conversationId}
                  >
                    Hold to Speak
                  </Button>
                ) : (
                  <Button
                    variant="normal"
                    iconName="status-stopped"
                    onClick={stopRecording}
                  >
                    Release to Send
                  </Button>
                )}
              </Box>

              {isProcessing && (
                <ProgressBar
                  status="in-progress"
                  label="Processing your voice..."
                />
              )}

              <Alert type="info">
                <strong>How to use:</strong> Click "Hold to Speak", talk naturally
                about your order, then release when done. The assistant will guide
                you through the process.
              </Alert>

              {/* Progress indicator */}
              {collectedFields.length > 0 && (
                <Box>
                  <Box variant="awsui-key-label">Collection Progress</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {collectedFields.map((field, idx) => (
                      <Badge key={idx} color="green">{field.replace('_', ' ')}</Badge>
                    ))}
                    {missingFields.length > 0 && (
                      <Badge color="grey">+{missingFields.length} more needed</Badge>
                    )}
                  </SpaceBetween>
                </Box>
              )}
            </SpaceBetween>
          </Container>

          {/* Order Data Preview */}
          {Object.keys(orderData).length > 0 && (
            <Container header={<Header variant="h3">Collected Information</Header>}>
              <SpaceBetween size="m">
                {/* Product Section */}
                {orderData.product_name && (
                  <div>
                    <Box variant="h4">Product Details</Box>
                    <ColumnLayout columns={3} variant="text-grid">
                      <div>
                        <Box variant="awsui-key-label">Product</Box>
                        <div>{orderData.product_name}</div>
                      </div>
                      {orderData.quantity && (
                        <div>
                          <Box variant="awsui-key-label">Quantity</Box>
                          <div>{orderData.quantity}</div>
                        </div>
                      )}
                      {orderData.size && (
                        <div>
                          <Box variant="awsui-key-label">Size</Box>
                          <div>{orderData.size}</div>
                        </div>
                      )}
                      {orderData.color && (
                        <div>
                          <Box variant="awsui-key-label">Color</Box>
                          <div>{orderData.color}</div>
                        </div>
                      )}
                      {orderData.retailer && (
                        <div>
                          <Box variant="awsui-key-label">Retailer</Box>
                          <div>{orderData.retailer}</div>
                        </div>
                      )}
                    </ColumnLayout>
                  </div>
                )}

                {/* Customer Section */}
                {orderData.customer_name && (
                  <div>
                    <Box variant="h4">Customer Information</Box>
                    <ColumnLayout columns={3} variant="text-grid">
                      <div>
                        <Box variant="awsui-key-label">Name</Box>
                        <div>{orderData.customer_name}</div>
                      </div>
                      {orderData.customer_email && (
                        <div>
                          <Box variant="awsui-key-label">Email</Box>
                          <div>{orderData.customer_email}</div>
                        </div>
                      )}
                      {orderData.phone && (
                        <div>
                          <Box variant="awsui-key-label">Phone</Box>
                          <div>{orderData.phone}</div>
                        </div>
                      )}
                    </ColumnLayout>
                  </div>
                )}

                {/* Shipping Address Section */}
                {orderData.street && (
                  <div>
                    <Box variant="h4">Shipping Address</Box>
                    <ColumnLayout columns={2} variant="text-grid">
                      <div>
                        <Box variant="awsui-key-label">Street</Box>
                        <div>{orderData.street}</div>
                      </div>
                      {orderData.city && (
                        <div>
                          <Box variant="awsui-key-label">City</Box>
                          <div>{orderData.city}</div>
                        </div>
                      )}
                      {orderData.state && (
                        <div>
                          <Box variant="awsui-key-label">State</Box>
                          <div>{orderData.state}</div>
                        </div>
                      )}
                      {orderData.postal_code && (
                        <div>
                          <Box variant="awsui-key-label">ZIP Code</Box>
                          <div>{orderData.postal_code}</div>
                        </div>
                      )}
                    </ColumnLayout>
                  </div>
                )}
              </SpaceBetween>
            </Container>
          )}

          {/* Conversation History */}
          <Container header={<Header variant="h3">Conversation</Header>}>
            <div style={{ 
              maxHeight: '300px', 
              overflowY: 'auto',
              padding: '10px',
              backgroundColor: '#f9f9f9',
              borderRadius: '4px'
            }}>
              {conversationHistory.map((message, index) => (
                <Box key={index} margin={{ bottom: 'm' }}>
                  <Box variant="awsui-key-label">
                    {message.role === 'user' ? '👤 You' : '🤖 Assistant'}
                  </Box>
                  <Box
                    padding={{ vertical: 's', horizontal: 'm' }}
                    backgroundColor={message.role === 'user' ? '#e3f2fd' : '#f5f5f5'}
                    borderRadius="8px"
                  >
                    {message.text}
                  </Box>
                </Box>
              ))}
            </div>
          </Container>
        </SpaceBetween>
      </Modal>
    </>
  );
};

export default VoiceOrderAssistant;
