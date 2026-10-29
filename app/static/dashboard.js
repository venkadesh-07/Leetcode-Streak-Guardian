// LeetCode Streak Guardian - Dashboard Client Logic
// Strictly CSP compliant: runs from static script file with no inline code.

document.addEventListener("DOMContentLoaded", function () {

    // ── 1. Activity Check Button Cooldown ─────────────────────────────────────
    const btn = document.getElementById("check-activity-btn");
    const form = document.getElementById("check-activity-form");

    if (btn) {
        const originalText = btn.textContent;
        let remaining = parseInt(btn.getAttribute("data-cooldown") || "0", 10);

        function startCooldown(seconds) {
            let count = seconds;
            btn.disabled = true;
            btn.classList.add("btn-disabled");
            btn.textContent = "Cooldown active (" + count + "s)";

            const interval = setInterval(function () {
                count -= 1;
                if (count <= 0) {
                    clearInterval(interval);
                    btn.disabled = false;
                    btn.classList.remove("btn-disabled");
                    btn.textContent = originalText;
                } else {
                    btn.textContent = "Cooldown active (" + count + "s)";
                }
            }, 1000);
        }

        if (remaining > 0) {
            startCooldown(remaining);
        }

        if (form) {
            form.addEventListener("submit", function () {
                btn.disabled = true;
                btn.classList.add("btn-disabled");
                btn.textContent = "Connecting to LeetCode...";
            });
        }
    }

    // ── 2. Live Countdown Timer ───────────────────────────────────────────────
    const countdownMetric = document.getElementById("countdown-metric");
    const countdownDisplay = document.getElementById("countdown-display");

    if (countdownMetric && countdownDisplay) {
        const resetEpochMs = parseInt(countdownMetric.getAttribute("data-reset-epoch") || "0", 10);

        if (resetEpochMs > 0) {
            function formatCountdown(totalSeconds) {
                if (totalSeconds <= 0) return "00:00:00";
                const h = Math.floor(totalSeconds / 3600);
                const m = Math.floor((totalSeconds % 3600) / 60);
                const s = totalSeconds % 60;
                const pad = function (n) { return String(n).padStart(2, "0"); };
                if (h > 0) return h + "h " + pad(m) + "m " + pad(s) + "s";
                if (m > 0) return pad(m) + "m " + pad(s) + "s";
                return pad(s) + "s";
            }

            function getUrgencyClass(totalSeconds) {
                if (totalSeconds <= 3600) return "countdown-critical";   // ≤ 1 hour
                if (totalSeconds <= 14400) return "countdown-urgent";     // ≤ 4 hours
                return "countdown-warning";                               // safe zone
            }

            function tick() {
                const nowMs = Date.now();
                const diffMs = resetEpochMs - nowMs;
                const diffSec = Math.max(0, Math.floor(diffMs / 1000));

                const label = diffSec === 0 ? "🔄 Resetting..." : "⏰ " + formatCountdown(diffSec);
                countdownDisplay.textContent = label;

                // Remove all urgency classes then apply the right one
                countdownMetric.classList.remove("countdown-critical", "countdown-urgent", "countdown-warning");
                countdownMetric.classList.add(getUrgencyClass(diffSec));

                if (diffSec === 0) {
                    // Stop ticking; page will refresh naturally on next user action
                    return;
                }
                setTimeout(tick, 1000);
            }

            tick();
        }
    }

});
