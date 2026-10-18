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

    // Desktop Companion Token Clipboard Copy
    const copyBtn = document.getElementById("copy-token-btn");
    const tokenInput = document.getElementById("desktop-sync-token");
    if (copyBtn && tokenInput) {
        copyBtn.addEventListener("click", function () {
            if (!tokenInput.value) return;
            navigator.clipboard.writeText(tokenInput.value).then(function () {
                const prevHtml = copyBtn.innerHTML;
                copyBtn.classList.remove("btn-primary");
                copyBtn.classList.add("btn-success");
                copyBtn.innerHTML = "<span>✓ Copied!</span>";
                setTimeout(function () {
                    copyBtn.classList.remove("btn-success");
                    copyBtn.classList.add("btn-primary");
                    copyBtn.innerHTML = prevHtml;
                }, 2000);
            }).catch(function () {
                tokenInput.select();
                document.execCommand("copy");
            });
        });
    }

    // Regenerate Token Form Confirmation
    const regenForm = document.getElementById("regenerate-token-form");
    if (regenForm) {
        regenForm.addEventListener("submit", function (e) {
            if (!confirm("Regenerate your sync token? You will need to update it in your desktop companion.")) {
                e.preventDefault();
            }
        });
    }
});
