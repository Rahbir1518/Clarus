import { SignIn } from "@clerk/nextjs";

const clerkAppearance = {
  variables: {
    colorPrimary: "#C43B3B",
    colorBackground: "#F8F9F6",
    colorText: "#1A1118",
    colorTextSecondary: "#7A6E75",
    colorInputBackground: "#F2F4F0",
    colorInputText: "#1A1118",
    borderRadius: "0.75rem",
  },
  elements: {
    card: "shadow-xl border border-border",
    headerTitle: "font-serif text-2xl",
    headerSubtitle: "text-muted-foreground",
    formButtonPrimary:
      "bg-primary hover:bg-primary/90 text-primary-foreground transition-colors",
    footerActionLink: "text-primary hover:text-primary/80",
    identityPreviewEditButton: "text-primary",
    formFieldInput:
      "border-border bg-muted/40 focus:border-primary focus:ring-primary/20",
    dividerLine: "bg-border",
    dividerText: "text-muted-foreground text-xs",
    socialButtonsBlockButton:
      "border-border bg-card hover:bg-muted transition-colors text-foreground",
  },
};

export default function SignInPage() {
  return <SignIn appearance={clerkAppearance} />;
}