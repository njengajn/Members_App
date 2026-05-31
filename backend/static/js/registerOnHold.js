// ============================================
// REGISTER STEP 1 (AJAX)
// ============================================

document.addEventListener("DOMContentLoaded", function () {

    const form = document.getElementById("registerStep1Form");
    if (!form) return; // safety

    form.addEventListener("submit", function (e) {
        e.preventDefault();

        const formData = new FormData(form);

        fetch("/members/ajax/register/", {
            method: "POST",
            body: formData
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === "ok") {
                window.location.href = "/members/register/verify-email/";
            } else {
                alert(data.message);
            }
        });
    });

});
