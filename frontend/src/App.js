import React, { useRef, useState, useEffect, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import {
  AppLayout,
  TopNavigation,
  SideNavigation,
  BreadcrumbGroup,
  Flashbar,
  HelpPanel,
  Link
} from '@cloudscape-design/components';
import '@cloudscape-design/global-styles/index.css';

// Import error suppression utility
import './utils/errorSuppression';

// Components
import OrderDashboard from './components/OrderDashboard';
// OrderHistory removed - functionality merged into OrderDashboard
import Settings from './pages/Settings';

// Pages
import ReviewQueue from './pages/ReviewQueue';
import FailedOrders from './pages/FailedOrders';
import OrderDetails from './pages/OrderDetails';
import CreateOrder from './pages/CreateOrder';
import BatchUpload from './pages/BatchUpload';
import SecretVault from './pages/SecretVault';
// MockShop removed - using static HTML files

function AppContent() {
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const appLayout = useRef();
  const location = useLocation();
  const navigate = useNavigate();

  // Get active nav item from current path
  const getActiveNavItem = () => {
    const path = location.pathname;
    if (path.startsWith('/orders/')) return 'dashboard';
    if (path === '/review') return 'review';
    if (path === '/failed') return 'failed';
    if (path === '/settings') return 'settings';
    return 'dashboard';
  };

  const activeNavItem = getActiveNavItem();

  const addNotification = useCallback((notification) => {
    const id = Date.now().toString();

    // Handle both old and new notification formats
    const normalizedNotification = typeof notification === 'string' ?
      { type: 'info', content: notification } : notification;

    const fullNotification = {
      ...normalizedNotification,
      id,
      dismissible: true,
      onDismiss: () => setNotifications(prev => prev.filter(n => n.id !== id))
    };

    setNotifications(prev => [...prev, fullNotification]);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  }, []);

  // WebSocket connection for real-time updates
  useEffect(() => {
    let ws = null;
    let reconnectTimeout = null;

    const connectWebSocket = () => {
      try {
        ws = new WebSocket('ws://localhost:8000/ws');

        ws.onopen = () => {
          setConnectionStatus('connected');
        };

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.type === 'order_progress') {
            // Handle real-time updates
            console.log('Real-time update:', data);
          }
        };

        ws.onclose = () => {
          setConnectionStatus('disconnected');
          // Only reconnect if not manually closed
          if (ws && ws.readyState !== WebSocket.CLOSED) {
            reconnectTimeout = setTimeout(connectWebSocket, 3000);
          }
        };

        ws.onerror = () => {
          setConnectionStatus('error');
        };

      } catch (error) {
        setConnectionStatus('error');
        console.error('WebSocket connection failed:', error);
      }
    };

    connectWebSocket();

    // Cleanup function
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (ws) {
        ws.close();
      }
    };
  }, [addNotification]);

  const navigationItems = [
    {
      type: 'section',
      text: 'Order Management',
      items: [
        { type: 'link', text: 'Dashboard', href: '/dashboard' }
      ]
    },
    { type: 'divider' },
    {
      type: 'section',
      text: 'Human Review',
      items: [
        { type: 'link', text: 'Review Queue', href: '/review' },
        { type: 'link', text: 'Failed Orders', href: '/failed' }
      ]
    },
    { type: 'divider' },
    {
      type: 'section',
      text: 'Configuration',
      items: [
        { type: 'link', text: 'Settings', href: '/settings' },
        { type: 'link', text: 'Secret Vault', href: '/secrets' }
      ]
    }
  ];

  const topNavigationUtilities = [
    {
      type: 'button',
      text: connectionStatus === 'connected' ? 'Connected' :
        connectionStatus === 'connecting' ? 'Connecting...' : 'Disconnected',
      iconName: connectionStatus === 'connected' ? 'status-positive' :
        connectionStatus === 'connecting' ? 'status-in-progress' : 'status-negative',
      variant: connectionStatus === 'connected' ? 'normal' : 'primary'
    }
  ];

  const getBreadcrumbs = () => {
    const baseBreadcrumb = { text: 'Drishti AI Navigator', href: '/dashboard' };
    const path = location.pathname;

    if (path.startsWith('/orders/')) {
      const orderId = path.split('/')[2];
      return [
        baseBreadcrumb,
        { text: 'Order Details', href: `/orders/${orderId}` }
      ];
    }

    switch (activeNavItem) {
      case 'review':
        return [baseBreadcrumb, { text: 'Human Review', href: '/review' }];
      case 'failed':
        return [baseBreadcrumb, { text: 'Failed Orders', href: '/failed' }];
      case 'settings':
        return [baseBreadcrumb, { text: 'Settings', href: '/settings' }];
      case 'secrets':
        return [baseBreadcrumb, { text: 'Secret Vault', href: '/secrets' }];
      default:
        return [baseBreadcrumb];
    }
  };

  const getHelpContent = () => {
    switch (activeNavItem) {
      case 'dashboard':
        return (
          <HelpPanel
            header={<h2>Drishti AI Navigator Dashboard</h2>}
            footer={
              <div>
                <h3>Learn more</h3>
                <ul>
                  <li><Link external href="https://aws.amazon.com/bedrock/">Amazon Bedrock</Link></li>
                  <li><Link external href="https://aws.amazon.com/bedrock/agentcore/">Bedrock AgentCore</Link></li>
                  <li><Link external href="https://github.com/anthropics/anthropic-sdk-python">Nova Act SDK</Link></li>
                </ul>
              </div>
            }
          >
            <div>
              <p>This dashboard demonstrates AI-powered Drishti AI Navigator for retailers using advanced browser automation:</p>

              <h3>Automation Methods</h3>
              <ul>
                <li><strong>Strands:</strong> AI agents with browser tools for intelligent e-commerce automation</li>
                <li><strong>Nova Act:</strong> Natural language browser automation with AgentCore integration</li>
              </ul>

              <h3>Key Features</h3>
              <ul>
                <li><strong>Real-time Monitoring:</strong> Live browser session viewing and progress tracking</li>
                <li><strong>Session Replay:</strong> Complete session recording and playback capabilities</li>
                <li><strong>Manual Control:</strong> Take control of browser sessions when needed</li>
                <li><strong>Screenshot Documentation:</strong> Automatic step-by-step visual documentation</li>
                <li><strong>Human-in-the-Loop:</strong> Automatic escalation for complex scenarios</li>
              </ul>

              <h3>Getting Started</h3>
              <ol>
                <li>Click "Create Order" to start an automation</li>
                <li>Choose between Strands or Nova Act automation methods</li>
                <li>Monitor progress with live browser viewing</li>
                <li>Review session replays and screenshots</li>
                <li>Take manual control when needed</li>
              </ol>
            </div>
          </HelpPanel>
        );

      case 'history':
        return (
          <HelpPanel
            header={<h2>Order History</h2>}
          >
            <div>
              <p>Complete history of all Drishti AI Navigator attempts with detailed status tracking.</p>

              <h3>Order Statuses</h3>
              <ul>
                <li><strong>Pending:</strong> Order queued for processing</li>
                <li><strong>Processing:</strong> Automation currently in progress</li>
                <li><strong>Completed:</strong> Order successfully completed</li>
                <li><strong>Failed:</strong> Automation failed, requires investigation</li>
                <li><strong>Requires Review:</strong> Human intervention needed</li>
                <li><strong>Cancelled:</strong> Order cancelled by user</li>
              </ul>

              <h3>Filtering & Search</h3>
              <ul>
                <li>Filter by retailer, status, or automation method</li>
                <li>Search by customer name or product</li>
                <li>Sort by creation date, completion time, or price</li>
              </ul>
            </div>
          </HelpPanel>
        );

      case 'review':
        return (
          <HelpPanel
            header={<h2>Review Queue</h2>}
          >
            <div>
              <p>Orders requiring human review due to automation issues or complex scenarios.</p>

              <h3>Common Review Triggers</h3>
              <ul>
                <li><strong>CAPTCHA Detection:</strong> Complex verification challenges</li>
                <li><strong>Payment Issues:</strong> Card declined or verification required</li>
                <li><strong>Out of Stock:</strong> Product unavailable in selected options</li>
                <li><strong>Account Issues:</strong> Login problems or account verification</li>
              </ul>

              <h3>Review Actions</h3>
              <ul>
                <li><strong>Complete Review:</strong> Mark as resolved and continue processing</li>
                <li><strong>Retry Order:</strong> Attempt automation again</li>
                <li><strong>Cancel Order:</strong> Cancel due to unresolvable issues</li>
              </ul>
            </div>
          </HelpPanel>
        );

      case 'failed':
        return (
          <HelpPanel
            header={<h2>Failed Orders</h2>}
          >
            <div>
              <p>Orders that failed during automation processing and require investigation.</p>

              <h3>Common Failure Reasons</h3>
              <ul>
                <li><strong>Network Issues:</strong> Connection timeouts or server errors</li>
                <li><strong>Site Changes:</strong> Website structure modifications</li>
                <li><strong>Product Issues:</strong> Item no longer available or pricing changes</li>
                <li><strong>Payment Failures:</strong> Card processing errors</li>
              </ul>

              <h3>Recovery Options</h3>
              <ul>
                <li><strong>Retry:</strong> Queue order for another automation attempt</li>
                <li><strong>Manual Processing:</strong> Complete order manually</li>
                <li><strong>Customer Contact:</strong> Notify customer of issues</li>
              </ul>
            </div>
          </HelpPanel>
        );

      case 'settings':
        return (
          <HelpPanel
            header={<h2>System Settings</h2>}
          >
            <div>
              <p>Configure system-wide settings for Drishti AI Navigator and AI models.</p>

              <h3>AI Model Configuration</h3>
              <ul>
                <li><strong>Default Models:</strong> Set preferred AI models for different automation methods</li>
                <li><strong>Model Parameters:</strong> Configure temperature, max tokens, and other model settings</li>
                <li><strong>Fallback Models:</strong> Define backup models when primary models are unavailable</li>
              </ul>

              <h3>Retailer Configuration</h3>
              <ul>
                <li><strong>Retailer URLs:</strong> Manage starting URLs for different retailers</li>
                <li><strong>Site-specific Settings:</strong> Configure automation parameters per retailer</li>
                <li><strong>Default Options:</strong> Set preferred retailers and automation methods</li>
              </ul>

              <h3>System Configuration</h3>
              <ul>
                <li><strong>Timeout Settings:</strong> Configure automation timeouts and retry limits</li>
                <li><strong>Notification Settings:</strong> Set up alerts and notifications</li>
                <li><strong>Logging Level:</strong> Adjust system logging verbosity</li>
              </ul>
            </div>
          </HelpPanel>
        );

      case 'secrets':
        return (
          <HelpPanel
            header={<h2>Secret Vault</h2>}
          >
            <div>
              <p>Securely manage login credentials for retailer websites used in automation.</p>

              <h3>Credential Management</h3>
              <ul>
                <li><strong>Add Credentials:</strong> Store username/password for retailer sites</li>
                <li><strong>Site Matching:</strong> Credentials are automatically matched to retailers</li>
                <li><strong>Secure Storage:</strong> All passwords are encrypted at rest</li>
                <li><strong>Status Indicators:</strong> See which credentials are active and working</li>
              </ul>

              <h3>Security Features</h3>
              <ul>
                <li><strong>Encryption:</strong> AES-256 encryption for all stored passwords</li>
                <li><strong>Access Control:</strong> Credentials only accessible during automation</li>
                <li><strong>Audit Trail:</strong> Track when credentials are used</li>
                <li><strong>Expiration:</strong> Set expiration dates for temporary credentials</li>
              </ul>

              <h3>Best Practices</h3>
              <ul>
                <li><strong>Unique Passwords:</strong> Use unique passwords for each retailer</li>
                <li><strong>Regular Updates:</strong> Update credentials periodically</li>
                <li><strong>Test Credentials:</strong> Verify credentials work before automation</li>
                <li><strong>Remove Unused:</strong> Delete credentials for inactive retailers</li>
              </ul>
            </div>
          </HelpPanel>
        );

      default:
        return null;
    }
  };

  const renderContent = () => {
    return (
      <Routes>
        <Route path="/" element={<OrderDashboard addNotification={addNotification} />} />
        <Route path="/dashboard" element={<OrderDashboard addNotification={addNotification} />} />
        <Route path="/orders/create" element={<CreateOrder addNotification={addNotification} />} />
        <Route path="/orders/batch-upload" element={<BatchUpload addNotification={addNotification} />} />
        <Route path="/orders/:orderId" element={<OrderDetails addNotification={addNotification} />} />

        <Route path="/review" element={<ReviewQueue addNotification={addNotification} />} />
        <Route path="/failed" element={<FailedOrders addNotification={addNotification} />} />
        <Route path="/settings" element={<Settings addNotification={addNotification} />} />
        <Route path="/secrets" element={<SecretVault addNotification={addNotification} />} />
      </Routes>
    );
  };

  return (
    <>
      <TopNavigation
        identity={{
          href: '/dashboard',
          title: 'Drishti AI Navigator'
        }}
        utilities={topNavigationUtilities}
      />

      <AppLayout
        ref={appLayout}
        contentType="default"
        breadcrumbs={
          <BreadcrumbGroup
            items={getBreadcrumbs()}
            expandAriaLabel="Show path"
            ariaLabel="Breadcrumbs"
            onFollow={(event) => {
              if (!event.detail.external) {
                event.preventDefault();
                navigate(event.detail.href);
              }
            }}
          />
        }
        navigation={
          <SideNavigation
            activeHref={location.pathname === '/' ? '/dashboard' : location.pathname}
            header={{
              href: '/dashboard',
              text: 'Drishti AI Navigator'
            }}
            items={navigationItems}
            onFollow={(event) => {
              if (!event.detail.external) {
                event.preventDefault();
                navigate(event.detail.href);
              }
            }}
          />
        }
        navigationOpen={navigationOpen}
        onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
        tools={getHelpContent()}
        toolsOpen={toolsOpen}
        onToolsChange={({ detail }) => setToolsOpen(detail.open)}
        notifications={notifications.length > 0 && <Flashbar items={notifications} />}
        content={renderContent()}
      />
    </>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/shop" element={<div>Redirecting to shop...</div>} />
        <Route path="*" element={<AppContent />} />
      </Routes>
    </Router>
  );
}

export default App;