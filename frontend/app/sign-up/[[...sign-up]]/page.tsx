import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="auth-page">
      <SignUp />
    </main>
  );
}
