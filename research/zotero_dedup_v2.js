// === Zotero Dedup: C246 文献调研 (2026-08-06 imports only) ===
// Self-contained: no external IDs needed

async function dedupCollection() {
    var libID = Zotero.Libraries.userLibraryID;
    var col = Zotero.Collections.getByLibraryAndKey(libID, 'K3GSQR4X');
    if (!col) return JSON.stringify({error: 'Collection K3GSQR4X not found'});

    var items = await col.getChildItems(false, false, true); // top-level only
    // Filter to 2026-08-06
    var ours = items.filter(function(it) {
        return it.dateAdded.startsWith('2026-08-06');
    });

    // Normalize title
    function norm(t) {
        return (t || '').toLowerCase().replace(/[^a-z0-9]/g, '').substring(0, 80);
    }

    // Group by normalized title
    var groups = {};
    for (var i = 0; i < ours.length; i++) {
        var nt = norm(ours[i].getField('title'));
        if (!nt) continue;
        if (!groups[nt]) groups[nt] = [];
        groups[nt].push(ours[i]);
    }

    // Find duplicates: for each group with >1, keep richest, trash rest
    var toTrashIDs = [];
    var dupGroups = 0;
    for (var nt in groups) {
        var group = groups[nt];
        if (group.length <= 1) continue;
        dupGroups++;

        // Sort by metadata richness (creators + abstract + date + DOI)
        function richness(it) {
            var score = 0;
            if (it.getCreators().length > 0) score += 2;
            if (it.getField('abstractNote')) score += 1;
            if (it.getField('date')) score += 1;
            if (it.getField('DOI')) score += 1;
            if (it.getField('url')) score += 1;
            if (it.getField('publicationTitle')) score += 1;
            return score;
        }
        group.sort(function(a, b) {
            return richness(b) - richness(a);
        });

        // Keep first, trash rest
        for (var j = 1; j < group.length; j++) {
            toTrashIDs.push(group[j].id);
        }
    }

    // Trash in batches
    var ok = 0, fail = 0;
    for (var i = 0; i < toTrashIDs.length; i += 50) {
        var batch = toTrashIDs.slice(i, i + 50);
        try {
            await Zotero.Items.trashTx(batch);
            ok += batch.length;
        } catch(e) {
            fail += batch.length;
        }
        await Zotero.Promise.delay(100);
    }

    return JSON.stringify({
        scanned: ours.length,
        dupGroups: dupGroups,
        toTrash: toTrashIDs.length,
        trashed: ok,
        failed: fail
    });
}

return await dedupCollection();