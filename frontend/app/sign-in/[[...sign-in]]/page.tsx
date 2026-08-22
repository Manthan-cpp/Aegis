import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="auth-page">
      <SignIn />
    </main>
  );
}
