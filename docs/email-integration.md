# Aegis email help integration

This is the hackathon-demo setup. The Women’s Support option is deliberately routed to **manthanjswl@gmail.com**, the demo inbox supplied by the project owner. It does not contact a real authority.

## 1. Create the EmailJS connection

1. Open [EmailJS](https://www.emailjs.com/) and create or sign in to an account.
2. Add a Gmail service and connect the demo Gmail account.
3. Create one email template.
4. Copy the EmailJS **Service ID**, **Template ID**, and **Public Key**. These are the only EmailJS values Aegis needs. Never put a Gmail password, OAuth secret, or private key in the project.

## 2. Configure the template

In the EmailJS template, set the recipient field to the dynamic variable `{{to_email}}`. The app sends these template variables:

- `to_email`
- `to_name`
- `from_name`
- `subject`
- `recipient_type`
- `user_name`
- `location`
- `situation`
- `instructions`
- `chat_summary`
- `demo_notice`
- `sent_at`

Use this body in the template:

```text
{{demo_notice}}

Hello,

Aegis received a help request.

Name: {{user_name}}
Recipient type: {{recipient_type}}
Location: {{location}}

Situation:
{{situation}}

Specific instructions:
{{instructions}}

Chat summary:
{{chat_summary}}

Sent at: {{sent_at}}
```

## 3. Add the IDs to the backend

Open `backend/.env` and fill in only these values:

```env
EMAILJS_SERVICE_ID=your_service_id
EMAILJS_TEMPLATE_ID=your_template_id
EMAILJS_PUBLIC_KEY=your_public_key
EMAILJS_PRIVATE_KEY=your_private_key
EMAIL_DEMO_MODE=true
EMAIL_DEMO_RECIPIENT=manthanjswl@gmail.com
```

Keep `EMAIL_DEMO_MODE=true` for the hackathon. In this mode, selecting “Women’s support inbox” always goes to the demo Gmail and the subject is marked `[DEMO]`. Selecting “Trusted person” uses the email entered in the form.

If EmailJS API access is set to **Strict**, `EMAILJS_PRIVATE_KEY` is required. It must remain in `backend/.env`; do not add it to the frontend, commit it, or share it in chat.

## 4. Restart and test

From the `aegis/backend` folder, restart the backend:

```powershell
.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8123
```

From `aegis/frontend`, restart the frontend if it is already running:

```powershell
npm run dev
```

Open Aegis through the calculator, choose **Email for help**, select the demo inbox, enter a name and situation, confirm the checkbox, and send. Do not use a real emergency situation for the demo.

## 5. Production change later

Before deployment, verify the intended authority address with the authority’s current official website and your legal/safety reviewer. Then change only the backend environment values:

```env
EMAIL_DEMO_MODE=false
EMAIL_WOMEN_SUPPORT_RECIPIENT=verified_authority_address@example.org
```

The frontend does not need to change. Keep the trusted-contact path available and ask the user to confirm the recipient before sending.

Email is not an emergency channel. The UI reminds users to share only information that is safe to send; immediate danger should be handled through the appropriate local emergency service when safe.
