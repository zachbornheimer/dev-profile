# RapidSign voice IVR ceremony script

Bounded instructions for a human or Grok voice agent calling `+12727703377`.

1. Wait for the greeting asking for the application / call-in code.
2. Enter the **6-digit code** on the keypad only (no speech).
3. When asked for your name, **speak the legal name** clearly, then stop.
4. After each disclosure, when told “press 1 to continue, or 2 to repeat”:
   - Press **1** to continue (or **2** once to hear it again).
5. Wait for “signing session is now complete” (or equivalent), then hang up.
6. Do **not** invent extra steps. Do not discuss other topics.

Do not expect an MP3 download until the call has hung up and the recording
callback has run (`CallSid` required for correlation).
