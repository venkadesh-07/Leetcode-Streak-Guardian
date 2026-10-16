// LeetCode Streak Guardian - Dashboard Client Logic
// Strictly CSP compliant: runs from static script file with no inline code.

document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("check-activity-btn");
    const form = document.getElementById("check-activity-form");
    if (!btn) return;

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
});
