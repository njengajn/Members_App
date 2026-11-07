
// ==========================================
// RETIRE MEMBER (ADMIN)
// ==========================================

function retireMember(memberId, coolingOffDays) {

    const reason = prompt(
        "Enter reason for retiring this member:"
    );

    if (!reason || reason.trim() === "") {
        alert("Retirement reason is required.");
        return false;
    }

    const confirmAction = confirm(
        "MEMBER RETIREMENT CONFIRMATION\n\n" +

        "You are about to RETIRE this member.\n\n" +

        "The following actions will take place:\n" +
        "- Member will be retired\n" +
        "- All dependants will be retired\n" +
        "- Member account will be locked\n\n" +

        "The configured claim cooling-off period is " +
        coolingOffDays + " days.\n\n" +

        "Retirement will not delete the configured " +
        "cooling-off period or historical activation date.\n\n" +

        "Retirement reason:\n" + reason.trim() + "\n\n" +

        "Do you want to continue?"
    );

    if (!confirmAction) {
        return false;
    }

    window.location.href =
        `/admin-panel/members/${memberId}/retire/?reason=` +
        encodeURIComponent(reason.trim());

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