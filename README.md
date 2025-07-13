# Budget Pay API

Budget Pay is a comprehensive budget management application that helps users track expenses, manage transactions, set saving goals, and get personalized financial insights.

## Features

- User authentication and profile management
  - Email/password authentication
  - Google OAuth login
- Expense tracking and categorization
- Transaction management
- Saving goals
- Budget allocation by category
- Dashboard with financial insights
- AI-powered financial chatbot

## Authentication Options

### Traditional Email/Password

Users can register and login using their email and password. Email verification is required to activate the account.

### Google OAuth

Users can sign in with their Google account. This provides a seamless login experience without requiring a separate password.

To set up Google OAuth:

1. Create a project in the Google Cloud Console
2. Configure the OAuth consent screen
3. Create OAuth client credentials
4. Set the following environment variables:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth client secret
   - `GOOGLE_REDIRECT_URI`: The callback URL (e.g., `https://your-api.com/api/v1/auth/google/callback`)

## AI Chatbot

The Budget Pay application includes an AI-powered chatbot that can:

1. Answer general finance and budgeting questions
2. Provide personalized insights based on the user's financial data
3. Help users make better financial decisions

The chatbot can answer questions like:
- "How much money do I have left to spend this week?"
- "What were my biggest expenses last month?"
- "How am I doing on my savings goals?"
- "What is the 50/30/20 budget rule?"
- "How can I save more money each month?"
