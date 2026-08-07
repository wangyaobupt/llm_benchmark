var keys = ["PURWSNPM", "Y7TQEAJ4", "UV3LVSU9", "2M8CMG2Q", "3SPL542B", "YA9IKYH8"];
var items = await Zotero.Items.getAsync(keys);
var ids = items.filter(it => it).map(it => it.id);
Zotero.Items.trashTx(ids);
return JSON.stringify({found: ids.length, keys: keys});