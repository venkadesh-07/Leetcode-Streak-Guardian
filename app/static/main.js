// LeetCode Streak Guardian - Global Client Utilities & Tactile Button Enhancer
// Strictly CSP Compliant: Runs from static script with zero inline code.

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    // ========================================================
    // 1. TACTILE BUTTON RIPPLE & PRESS-DOWN EFFECT
    // ========================================================
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".btn");
        if (!btn || btn.disabled || btn.classList.contains("btn-disabled")) return;

        // Add tactile micro-press feedback
        btn.classList.add("btn-pressed");
        setTimeout(function () {
            btn.classList.remove("btn-pressed");
        }, 120);

        // Calculate click coordinates for radial ripple wave
        const rect = btn.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height) * 1.8;
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        const ripple = document.createElement("span");
        ripple.className = "btn-ripple";
        ripple.style.width = size + "px";
        ripple.style.height = size + "px";
        ripple.style.left = x + "px";
        ripple.style.top = y + "px";

        btn.appendChild(ripple);

        setTimeout(function () {
            ripple.remove();
        }, 600);
    });

    // ========================================================
    // 2. FORM SUBMISSION ACTIVE FEEDBACK & SPINNER
    // ========================================================
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function (e) {
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!submitBtn || submitBtn.disabled || submitBtn.classList.contains("btn-disabled")) return;

            // Give tiny delay so ripple shows, then apply loading feedback
            setTimeout(function () {
                submitBtn.classList.add("btn-loading");

                if (submitBtn.tagName === "BUTTON") {
                    const originalHtml = submitBtn.innerHTML;
                    submitBtn.setAttribute("data-original-html", originalHtml);
                    submitBtn.innerHTML = '<span class="btn-spinner"></span>' + (submitBtn.getAttribute("data-loading-text") || "Processing...");
                } else if (submitBtn.tagName === "INPUT") {
                    submitBtn.setAttribute("data-original-val", submitBtn.value);
                    submitBtn.value = submitBtn.getAttribute("data-loading-text") || "Processing...";
                }
            }, 30);
        });
    });

    // ========================================================
    // 3. TELEGRAM 6-DIGIT PIN PAIRING & RADAR STATUS DETECTOR
    // ========================================================
    const connectTgBtn = document.getElementById("connect-telegram-btn");
    const tgRadar = document.getElementById("telegram-sync-radar");
    const tgBadge = document.getElementById("telegram-status-badge");
    const tgChatIdInput = document.getElementById("telegram_chat_id");
    const tgCheckbox = document.getElementById("notify_telegram");
    const copyPinBtn = document.getElementById("copy-pin-btn");
    const refreshPinBtn = document.getElementById("refresh-pin-btn");
    const copyTgCmdBtn = document.getElementById("copy-tg-cmd-btn");

    let pollTimer = null;
    let pollAttempts = 0;
    const maxPollAttempts = 120; // Poll for 5 minutes (every 2.5s)

    function checkTelegramStatus() {
        fetch("/api/telegram/check-link-status", {
            method: "GET",
            headers: { "Accept": "application/json" }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            pollAttempts++;
            if (data.status === "success" && data.linked) {
                if (pollTimer) clearInterval(pollTimer);
                pollTimer = null;

                // Update UI live!
                if (tgBadge) {
                    tgBadge.className = "badge";
                    tgBadge.style.background = "rgba(16, 185, 129, 0.15)";
                    tgBadge.style.color = "#34d399";
                    tgBadge.textContent = "🟢 Linked";
                }

                if (tgRadar) {
                    tgRadar.style.display = "block";
                    tgRadar.style.background = "rgba(16, 185, 129, 0.12)";
                    tgRadar.style.borderColor = "rgba(16, 185, 129, 0.35)";
                    tgRadar.style.color = "#a7f3d0";
                    tgRadar.innerHTML = '🎉 <strong>Telegram Connected!</strong> Chat ID: <code>' + (data.telegram_chat_id || '') + '</code> &bull; Streak alerts are now activated!';
                }

                if (tgChatIdInput) {
                    tgChatIdInput.value = data.telegram_chat_id || "";
                }

                if (tgCheckbox) {
                    tgCheckbox.checked = true;
                }

                if (connectTgBtn) {
                    connectTgBtn.className = "btn btn-success btn-sm";
                    connectTgBtn.innerHTML = "<span>✅ Connected!</span>";
                }

                // Reload page after 1.8s to fully refresh form and show squad status / test controls
                setTimeout(function () {
                    window.location.reload();
                }, 1800);
            } else if (pollAttempts >= maxPollAttempts) {
                if (pollTimer) clearInterval(pollTimer);
                pollTimer = null;
                if (tgRadar) {
                    tgRadar.innerHTML = '⏳ <em>Still listening for your PIN. Send the 6 digits in Telegram and refresh when ready.</em>';
                }
            }
        })
        .catch(function () {
            // Ignore network glitch during poll
        });
    }

    // Auto-listen if radar is present on screen (user is waiting to link)
    if (tgRadar) {
        pollTimer = setInterval(checkTelegramStatus, 2500);
    }

    if (connectTgBtn) {
        connectTgBtn.addEventListener("click", function () {
            if (tgRadar) {
                tgRadar.style.display = "block";
                tgRadar.innerHTML = '<span class="btn-spinner"></span> <strong>Opening Telegram...</strong> Send your 6-digit PIN in the chat! (Checking automatically)';
            }
            pollAttempts = 0;
            if (pollTimer) clearInterval(pollTimer);
            pollTimer = setInterval(checkTelegramStatus, 2000);
            setTimeout(checkTelegramStatus, 1500);
        });
    }

    const connectTgWebBtn = document.getElementById("connect-telegram-web-btn");
    if (connectTgWebBtn) {
        connectTgWebBtn.addEventListener("click", function () {
            if (tgRadar) {
                tgRadar.style.display = "block";
                tgRadar.innerHTML = '<span class="btn-spinner"></span> <strong>Opening Telegram Web...</strong> Send your 6-digit PIN in the chat! (Checking automatically)';
            }
            pollAttempts = 0;
            if (pollTimer) clearInterval(pollTimer);
            pollTimer = setInterval(checkTelegramStatus, 2000);
            setTimeout(checkTelegramStatus, 1500);
        });
    }

    // 1-Click Copy PIN
    if (copyPinBtn) {
        copyPinBtn.addEventListener("click", function () {
            const pinValEl = document.getElementById("telegram-pin-value");
            const pin = copyPinBtn.getAttribute("data-pin") || (pinValEl ? pinValEl.textContent.trim() : "");
            if (!pin) return;
            navigator.clipboard.writeText(pin).then(function () {
                const prevHtml = copyPinBtn.innerHTML;
                copyPinBtn.classList.remove("btn-secondary");
                copyPinBtn.classList.add("btn-success");
                copyPinBtn.innerHTML = "<span>✓ PIN Copied!</span>";
                setTimeout(function () {
                    copyPinBtn.classList.remove("btn-success");
                    copyPinBtn.classList.add("btn-secondary");
                    copyPinBtn.innerHTML = prevHtml;
                }, 2000);
            }).catch(function () {
                window.prompt("Your 6-digit Telegram Pairing PIN:", pin);
            });
        });
    }

    // Refresh PIN via AJAX
    if (refreshPinBtn) {
        refreshPinBtn.addEventListener("click", function () {
            const csrfTokenInput = document.querySelector('input[name="csrf_token"]');
            const csrfToken = csrfTokenInput ? csrfTokenInput.value : "";
            refreshPinBtn.disabled = true;
            refreshPinBtn.innerHTML = '<span class="btn-spinner"></span> Generating...';

            fetch("/api/telegram/refresh-pin", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                    "Accept": "application/json"
                }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                refreshPinBtn.disabled = false;
                refreshPinBtn.innerHTML = "<span>🔄 Refresh PIN</span>";
                if (data.status === "success" && data.pin) {
                    const pinValEl = document.getElementById("telegram-pin-value");
                    if (pinValEl) {
                        pinValEl.textContent = data.pin;
                        pinValEl.style.transition = "transform 0.2s ease";
                        pinValEl.style.transform = "scale(1.15)";
                        setTimeout(function () { pinValEl.style.transform = "scale(1)"; }, 250);
                    }
                    const pinHint = document.getElementById("pin-inline-hint");
                    if (pinHint) pinHint.textContent = data.pin;
                    if (copyPinBtn) copyPinBtn.setAttribute("data-pin", data.pin);
                }
            })
            .catch(function () {
                refreshPinBtn.disabled = false;
                refreshPinBtn.innerHTML = "<span>🔄 Refresh PIN</span>";
            });
        });
    }

    // Copy /link command
    if (copyTgCmdBtn) {
        copyTgCmdBtn.addEventListener("click", function () {
            const cmd = copyTgCmdBtn.getAttribute("data-cmd");
            if (!cmd) return;
            navigator.clipboard.writeText(cmd).then(function () {
                const prevHtml = copyTgCmdBtn.innerHTML;
                copyTgCmdBtn.classList.remove("btn-secondary");
                copyTgCmdBtn.classList.add("btn-success");
                copyTgCmdBtn.innerHTML = "<span>✓ Command Copied!</span>";
                setTimeout(function () {
                    copyTgCmdBtn.classList.remove("btn-success");
                    copyTgCmdBtn.classList.add("btn-secondary");
                    copyTgCmdBtn.innerHTML = prevHtml;
                }, 2000);
            }).catch(function () {
                window.prompt("Copy this command and paste it in your Telegram bot chat:", cmd);
            });
        });
    }


    // ========================================================
    // 4. FULL-BOUNDARY CLICKABLE TOGGLE FOR CHECKBOX GROUPS
    // ========================================================
    function syncCheckboxVisual(group, isChecked) {
        if (!group) return;
        if (isChecked) {
            group.classList.add("is-checked");
        } else {
            group.classList.remove("is-checked");
        }
        const switchTrack = group.querySelector(".toggle-switch-track");
        if (switchTrack) {
            if (isChecked) {
                switchTrack.classList.add("active");
            } else {
                switchTrack.classList.remove("active");
            }
        }
    }

    // Initialize all checkbox groups on page load
    document.querySelectorAll(".checkbox-group").forEach(function (group) {
        const checkbox = group.querySelector('input[type="checkbox"]');
        if (checkbox) {
            syncCheckboxVisual(group, checkbox.checked);
            checkbox.addEventListener("change", function () {
                syncCheckboxVisual(group, checkbox.checked);
            });
        }
    });

    // Delegate click on any checkbox-group boundary
    document.addEventListener("click", function (e) {
        const group = e.target.closest(".checkbox-group");
        if (!group) return;

        // Ignore clicks on nested interactive links or text inputs
        if (e.target.closest("a, button, input:not([type='checkbox']), select, textarea")) return;

        const checkbox = group.querySelector('input[type="checkbox"]');
        if (!checkbox || checkbox.disabled) return;

        // If clicked directly on the checkbox input, sync visual
        if (e.target === checkbox) {
            syncCheckboxVisual(group, checkbox.checked);
            return;
        }

        // If clicked anywhere else in the boundary, toggle checkbox state
        e.preventDefault();
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        syncCheckboxVisual(group, checkbox.checked);

        // Tactile ripple inside the checkbox-group boundary
        const rect = group.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height) * 1.5;
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        const ripple = document.createElement("span");
        ripple.className = "btn-ripple";
        ripple.style.width = size + "px";
        ripple.style.height = size + "px";
        ripple.style.left = x + "px";
        ripple.style.top = y + "px";
        group.appendChild(ripple);
        setTimeout(function () { ripple.remove(); }, 600);
    });

    // ========================================================
    // 5. DISCONNECT TELEGRAM ACTION HANDLER
    // ========================================================
    const disconnectTgBtn = document.getElementById("disconnect-telegram-btn");
    const disconnectTgForm = document.getElementById("disconnect-telegram-form");
    if (disconnectTgBtn && disconnectTgForm) {
        disconnectTgBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (window.confirm("Are you sure you want to unlink your Telegram account?")) {
                disconnectTgBtn.disabled = true;
                disconnectTgBtn.innerHTML = '<span class="btn-spinner"></span> Unlinking...';
                disconnectTgForm.submit();
            }
        });
    }
});
