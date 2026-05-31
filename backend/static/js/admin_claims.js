document.addEventListener("DOMContentLoaded", () => {

    const modal = document.getElementById("confirmModal");
    const uidSpan = document.getElementById("claimUid");
    let approveUrl = "";

    document.querySelectorAll(".btn-approve").forEach(btn => {
        btn.addEventListener("click", () => {
            approveUrl = `/members/admin/claims/${btn.dataset.id}/approve/`;
            uidSpan.textContent = btn.dataset.uid;
            modal.style.display = "block";
        });
    });

    document.getElementById("confirmYes").onclick = () => {
        window.location.href = approveUrl;
    };

    document.getElementById("confirmNo").onclick = () => {
        modal.style.display = "none";
    };

});
