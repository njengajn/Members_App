// ==========================================
// RETIRE MEMBER (ADMIN)
// ==========================================
function retireMember(memberId) {

    const reason = prompt("Enter reason for retiring this member:");

    if (!reason || reason.trim() === "") {
        alert("Retirement reason is required.");
        return false;
    }

    const confirmAction = confirm(
        "Are you sure you want to RETIRE this member?\n\n" +
        "- Member will be retired\n" +
        "- All dependants will be retired\n" +
        "- Account will be locked"
    );

    if (!confirmAction) return false;

    window.location.href =
        `/admin-panel/members/${memberId}/retire/?reason=` +
        encodeURIComponent(reason);

    return false;
}


function restoreMember(memberId) {

    const reason = prompt(
        "Enter reason for restoring this member:"
    );

    if (!reason || reason.trim() === "") {
        alert("Restore reason is required.");
        return false;
    }

    if (!confirm(
        "Restore this member and all dependants?"
    )) {
        return false;
    }

    window.location.href =
        `/admin-panel/members/${memberId}/restore/?reason=` +
        encodeURIComponent(reason);

    return false;
}