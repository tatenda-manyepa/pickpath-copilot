# RB-03 WMS to WCS message rejects

**Applies to:** WCS-401, WCS-402, WCS-410, WCS-420
**Typical symptom:** stations short of work; growing count of rejected tasks in the WCS.

## Steps
1. In the WCS interface monitor, filter rejects for the last 30 minutes and group them by code.
2. WCS-402 (unknown location): check whether a WMS slotting update ran shortly before the rejects began. If so, trigger **WCS location master resync**, then ask WMS support to resend rejected tasks.
3. WCS-401 (invalid SKU): trigger SKU master resync.
4. WCS-410 (schema): check whether either system was upgraded; escalate to WMS support with a sample message.
5. WCS-420 (duplicate): confirm a WMS failover; the WCS discards duplicates automatically. No action unless the rate keeps rising.
6. Confirm the reject rate returns to zero.

## Note
WCS-402 after slotting updates has happened repeatedly (INC-0131, INC-0139). An automated pre-check and alert is recommended.
