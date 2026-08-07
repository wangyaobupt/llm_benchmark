var keys = ["PURWSNPM", "Y7TQEAJ4", "UV3LVSU9"];
var items = await Zotero.Items.getAsync(keys);
var results = { keys_in: keys.length, items_found: items.length };
if (items.length > 0) {
    results.item0_key = items[0].key;
    results.item0_id = items[0].id;
    results.item0_deleted = items[0].deleted;
    try {
        await Zotero.Items.trashTx([items[0].id]);
        results.trash_result = 'OK';
    } catch(e) {
        results.trash_error = e.message ? e.message : String(e);
    }
} else {
    results.note = 'No items found';
}
return JSON.stringify(results, null, 2);