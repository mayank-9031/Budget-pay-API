# Budget Pay API

Budget Pay is a comprehensive budget management application that helps users track expenses, manage transactions, set saving goals, and get personalized financial insights.

## Features

- User Authentication (JWT, OAuth)
- Budget Management
- Expense Tracking
- Financial Goals
- Transaction Management
- AI-Powered Chatbot
- Real-time Notifications (WebSockets)
- AI-Generated Personalized Notifications

## Real-time Notification System

The application includes a comprehensive notification system with the following features:

### User-specific Notifications

All notifications are tied to specific users, ensuring data privacy and relevant information delivery.

### WebSocket Real-time Updates

Notifications are delivered in real-time via WebSockets, enabling instant updates without polling.

- Connect to the WebSocket endpoint: `/api/v1/notification/ws?token=YOUR_JWT_TOKEN`
- Receive real-time notification events as JSON objects
- Notifications include type, title, message, and other metadata

### AI-Generated Notifications

The system leverages OpenRouter API to generate personalized, intelligent notifications based on user data:

- Budget insights based on spending patterns
- Savings tips customized to user behavior
- Goal progress updates with personalized encouragement
- Overspending alerts with contextual information

### REST API Endpoints

The notification system exposes these REST endpoints:

- `GET /api/v1/notification/` - List user's notifications with optional filtering
- `GET /api/v1/notification/unread-count` - Get count of unread notifications
- `GET /api/v1/notification/{id}` - Get specific notification
- `POST /api/v1/notification/{id}/read` - Mark notification as read
- `POST /api/v1/notification/read_all` - Mark all notifications as read
- `POST /api/v1/notification/generate-ai` - Generate custom AI notification
- `POST /api/v1/notification/generate-budget-insight` - Generate AI budget insight

## Configuration

To enable AI-powered notifications, set the `OPENROUTER_API_KEY` environment variable with your OpenRouter API key.

## WebSocket Example (JavaScript)

```javascript
// Connect to notification WebSocket
const token = "your_jwt_token";
const ws = new WebSocket(`wss://api.budgetpay.com/api/v1/notification/ws?token=${token}`);

ws.onopen = () => {
  console.log("Connected to notification service");
};

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log("New notification:", notification);
  
  // Display notification to user
  showNotification(notification.data.title, notification.data.message);
};

ws.onclose = () => {
  console.log("Disconnected from notification service");
};

// Function to display notification
function showNotification(title, message) {
  // Implementation depends on your frontend
}
```

## AI-powered Notifications Example

```javascript
// Request an AI-generated budget insight
async function generateBudgetInsight() {
  const response = await fetch('/api/v1/notification/generate-budget-insight', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer YOUR_JWT_TOKEN',
      'Content-Type': 'application/json'
    }
  });
  
  const notification = await response.json();
  console.log("AI-generated insight:", notification);
}
```