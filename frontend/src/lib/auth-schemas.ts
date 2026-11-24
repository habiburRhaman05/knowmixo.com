import { z } from "zod";

// Keep these in sync with backend/app/auth/schemas.py. The backend is still
// authoritative; these schemas only give immediate feedback.

export const emailSchema = z
  .string()
  .trim()
  .min(1, "Enter your email.")
  .email("That doesn't look like a valid email.");

export const nameSchema = z
  .string()
  .trim()
  .min(1, "Enter your name.")
  .max(120, "Name is too long.");

/** Server minimum is 10 chars; we show the extra rules as advice only. */
export const newPasswordSchema = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(200, "That's too long.");

export const currentPasswordSchema = z
  .string()
  .min(1, "Enter your password.")
  .max(200, "That's too long.");

export const signupSchema = z.object({
  email: emailSchema,
  password: newPasswordSchema,
  name: nameSchema,
});

export const loginSchema = z.object({
  email: emailSchema,
  password: currentPasswordSchema,
});

export const forgotSchema = z.object({ email: emailSchema });

export const resetSchema = z
  .object({
    token: z.string().min(1, "This link is missing a token."),
    new_password: newPasswordSchema,
    confirm_password: z.string(),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords don't match.",
  });

export const changePasswordSchema = z
  .object({
    current_password: currentPasswordSchema,
    new_password: newPasswordSchema,
    confirm_password: z.string(),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords don't match.",
  });

export const resendSchema = z.object({ email: emailSchema });

export type SignupInput = z.infer<typeof signupSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type ForgotInput = z.infer<typeof forgotSchema>;
export type ResetInput = z.infer<typeof resetSchema>;
export type ResendInput = z.infer<typeof resendSchema>;
