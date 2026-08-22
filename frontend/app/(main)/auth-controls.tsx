"use client";

import {
  SignInButton,
  SignUpButton,
  UserButton,
  useUser,
} from "@clerk/nextjs";

const clerkConfigured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

function SignedInControls() {
  const { isLoaded, isSignedIn } = useUser();

  if (!isLoaded) return <span className="auth-guest-note">Account</span>;

  if (isSignedIn) {
    return (
      <div className="auth-user-control" aria-label="Your account">
        <span className="auth-user-label">Account</span>
        <UserButton />
      </div>
    );
  }

  return (
    <div className="auth-controls" aria-label="Account access">
      <span className="auth-guest-note">You can continue as a guest.</span>
      <SignInButton mode="modal">
        <button className="auth-button auth-button-quiet" type="button">Sign in</button>
      </SignInButton>
      <SignUpButton mode="modal">
        <button className="auth-button auth-button-primary" type="button">Create account</button>
      </SignUpButton>
    </div>
  );
}

export default function AuthControls() {
  if (!clerkConfigured) {
    return <span className="auth-guest-note">Guest access</span>;
  }

  return <SignedInControls />;
}
