// LeetCode Streak Guardian - Global Client Utilities & Tactile Button Enhancer
// Strictly CSP Compliant: Runs from static script with zero inline code.

document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    // ========================================================
    // 0. TOAST NOTIFICATION SYSTEM
    // ========================================================
    var toastContainer = document.createElement("div");
    toastContainer.id = "toast-container";
    document.body.appendChild(toastContainer);

    // Mark <body> so CSS hides the plain .alert fallbacks
    document.body.classList.add("js-toasts-active");

    var TOAST_ICONS = {
        success: "✅",
        warning: "⚠️",
        error:   "❌",
        info:    "ℹ️"
    };

    var TOAST_DURATIONS = {
        success: 5000,
        warning: 7000,
        error:   9000,
        info:    6000
    };

    function showToast(message, type, durationMs) {
        type = type || "info";
        durationMs = durationMs || TOAST_DURATIONS[type] || 5000;

        var toast = document.createElement("div");
        toast.className = "toast toast-" + type;
        toast.style.setProperty("--toast-duration", (durationMs / 1000) + "s");
        toast.setAttribute("role", "alert");
        toast.setAttribute("aria-live", "polite");

        var icon = document.createElement("span");
        icon.className = "toast-icon";
        icon.textContent = TOAST_ICONS[type] || "ℹ️";

        var body = document.createElement("span");
        body.className = "toast-body";
        body.textContent = message;

        var closeBtn = document.createElement("button");
        closeBtn.className = "toast-close";
        closeBtn.setAttribute("aria-label", "Dismiss");
        closeBtn.textContent = "✕";

        toast.appendChild(icon);
        toast.appendChild(body);
        toast.appendChild(closeBtn);
        toastContainer.appendChild(toast);

        function dismiss() {
            if (toast.classList.contains("toast-hiding")) return;
            toast.classList.add("toast-hiding");
            // Remove after out-animation completes (300ms)
            setTimeout(function () {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 320);
        }

        // Auto-dismiss after duration
        var autoDismiss = setTimeout(dismiss, durationMs);

        // Click anywhere on toast OR close button to dismiss immediately
        toast.addEventListener("click", function () {
            clearTimeout(autoDismiss);
            dismiss();
        });

        return toast;
    }

    // Expose globally so other scripts can call showToast()
    window.showToast = showToast;

    // Convert existing inline Flask flash .alert elements into toasts
    var flashAlerts = document.querySelectorAll(".alert[role='alert']");
    flashAlerts.forEach(function (alert) {
        var message = alert.textContent.trim();
        if (!message) return;

        // Map Flask alert category to toast type
        var type = "info";
        if (alert.classList.contains("alert-success")) type = "success";
        else if (alert.classList.contains("alert-warning")) type = "warning";
        else if (alert.classList.contains("alert-error"))   type = "error";

        // Small stagger so multiple toasts don't stack at once
        showToast(message, type);
    });

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

    // ========================================================
    // 6. PASSWORD VISIBILITY TOGGLE (EYE ICON)
    // ========================================================
    document.querySelectorAll(".toggle-password-btn").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const wrapper = btn.closest(".password-wrapper");
            if (!wrapper) return;
            const input = wrapper.querySelector("input");
            if (!input) return;

            const eyeOpen = btn.querySelector(".eye-open");
            const eyeClosed = btn.querySelector(".eye-closed");

            if (input.type === "password") {
                input.type = "text";
                if (eyeOpen) eyeOpen.style.display = "none";
                if (eyeClosed) eyeClosed.style.display = "inline-block";
                btn.setAttribute("aria-label", "Hide password");
                btn.style.color = "var(--brand-amber-light, #fbbf24)";
            } else {
                input.type = "password";
                if (eyeOpen) eyeOpen.style.display = "inline-block";
                if (eyeClosed) eyeClosed.style.display = "none";
                btn.setAttribute("aria-label", "Show password");
                btn.style.color = "var(--text-muted, #94a3b8)";
            }
        });
    });

    // ========================================================
    // 7. INLINE LEETCODE USERNAME VALIDATION
    // ========================================================
    const usernameInput = document.getElementById("leetcode-username-input");
    const usernameHint = document.getElementById("username-validation-hint");

    if (usernameInput && usernameHint) {
        let validationTimer = null;
        const originalValue = usernameInput.value.trim();

        function showHint(message, isValid, isLoading) {
            usernameHint.style.display = "block";
            usernameHint.textContent = message;
            if (isLoading) {
                usernameHint.style.background = "rgba(100, 116, 139, 0.12)";
                usernameHint.style.color = "var(--text-secondary)";
                usernameHint.style.border = "1px solid rgba(100, 116, 139, 0.25)";
            } else if (isValid) {
                usernameHint.style.background = "rgba(16, 185, 129, 0.10)";
                usernameHint.style.color = "#34d399";
                usernameHint.style.border = "1px solid rgba(16, 185, 129, 0.3)";
            } else {
                usernameHint.style.background = "rgba(239, 68, 68, 0.10)";
                usernameHint.style.color = "#f87171";
                usernameHint.style.border = "1px solid rgba(239, 68, 68, 0.3)";
            }
        }

        function hideHint() {
            usernameHint.style.display = "none";
            usernameHint.textContent = "";
        }

        function validateUsername(username) {
            showHint("⏳ Checking username on LeetCode...", false, true);
            fetch("/api/validate-username?username=" + encodeURIComponent(username), {
                method: "GET",
                headers: { "Accept": "application/json" }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.valid) {
                    showHint(data.message, true, false);
                } else {
                    showHint(data.message, false, false);
                }
            })
            .catch(function () {
                showHint("⚠️ Could not reach LeetCode right now. You can still save.", false, true);
            });
        }

        // Debounced validation as user types
        usernameInput.addEventListener("input", function () {
            clearTimeout(validationTimer);
            const val = usernameInput.value.trim();
            if (!val || val === originalValue) {
                hideHint();
                return;
            }
            // Wait 600ms after user stops typing before firing
            validationTimer = setTimeout(function () {
                if (val.length >= 2) validateUsername(val);
            }, 600);
        });

        // Immediate validation on blur (tab away / click out)
        usernameInput.addEventListener("blur", function () {
            clearTimeout(validationTimer);
            const val = usernameInput.value.trim();
            if (!val || val === originalValue) {
                hideHint();
                return;
            }
            if (val.length >= 2) validateUsername(val);
        });
    }

});
