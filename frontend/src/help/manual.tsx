/*
 * The MyERP user manual.
 *
 * Every pull request that adds or changes a screen updates its chapter here,
 * so the manual always matches what people see. Write for the person doing
 * the work: short steps, the words on the screen in quotes, no jargon.
 *
 * `pages` lists the screens a chapter belongs to (see `helpTopicFor` in
 * Help.tsx); the Help link in the top menu opens the chapter for the screen
 * the person is on.
 */
import type { ReactNode } from "react";

export type Chapter = {
  id: string;
  title: string;
  summary: string;
  body: ReactNode;
};

/** A list of fields: what each one on a form is for. */
function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="help-fields">
      <tbody>
        {rows.map(([name, what]) => (
          <tr key={name}>
            <th>{name}</th>
            <td>{what}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="help-note">{children}</p>;
}

export const MANUAL: Chapter[] = [
  {
    id: "start",
    title: "Getting started",
    summary: "Signing in, finding your way around and saving your work.",
    body: (
      <>
        <h3>Signing in</h3>
        <p>
          Open your company group's MyERP address and click "Sign in with
          Google". Use the Google account for the email address your MyERP admin
          added for you. If MyERP says your email "does not have access", ask
          the admin to add you under Users.
        </p>
        <p>
          To sign out, click "Sign out" at the top right. On a shared computer,
          always sign out when you finish.
        </p>

        <h3>Picking from a list</h3>
        <p>
          A box with a small down arrow at its right end opens a list. Wherever
          you pick a group, state, currency, credit term, salesman or
          an existing customer or supplier, click the box and start typing: the
          list narrows to what matches (type any part of the name, in any
          order). Use the up and down arrow keys and Enter, or click the one you
          want. Press Esc to close the list without changing it. The arrow
          points up and turns green while the list is open, and is faded on a
          box that is locked.
        </p>

        <h3>Adding a missing record from a list</h3>
        <p>
          If what you type in a list of customers' credit terms, units, item
          groups, brands, ledger groups, branches or transporters is not there,
          the list offers 'Create "<em>what you typed</em>"' at the bottom.
          Click it (or press Enter on it): that master's screen opens in a new
          browser tab with the "Add" form open and the name filled in, so
          nothing on the screen you were filling is lost. Fill in the rest and
          click "Save". The new tab closes by itself and the list on your first
          screen picks the new record. If the tab stays open (some browsers keep
          it), close it yourself; the record is still picked.
        </p>
        <Note>
          You see "Create" only if your role may add masters. The new record
          goes through all the usual checks, including "No duplicates" below.
        </Note>

        <h3>No duplicates</h3>
        <p>
          MyERP will not save a second record that means the same as one already
          there. Names are compared without capital letters and extra spaces, so
          "Acme Foods " and "ACME Foods" are the same name, and extra spaces are
          taken out when you save. Customers and suppliers, items, units, credit
          terms and roles must differ across the whole group; ledgers, ledger
          groups, branches and transporters must differ within their company. A
          GSTIN or a PAN can belong to one company only, a GSTIN to one customer
          or supplier only (add another address to that party instead), a bank
          account number to one bank ledger of a company, and a barcode to one
          item.
        </p>
        <p>
          When you try, the form says which record is already there, for example
          'There is already a unit with the name "Kilogram".', with a link "Open
          “Kilogram”" that takes you to it. Imports check every row the same
          way, including two rows of the same file.
        </p>

        <h3>The screen</h3>
        <ul>
          <li>
            <strong>Top menu</strong> (white bar): the modules you may use, such
            as Dashboard and Masters. You only see the ones your role allows.
            Click "Masters" to open its list: "Ledger groups", "Ledgers",
            "Credit terms", "Items", "Price lists" and "Units". Ledger groups and
            ledgers open for the company you are working in. Owners also see "Admin", which
            holds "Company", "Users", "User roles" and "Reset data". "Help"
            opens this manual at the page for the screen you are on.
          </li>
          <li>
            <strong>Company</strong> (top right, beside "Help"): the company you
            are working in. Check it before you enter anything. If there are
            several companies, click it to pick another; on a company's screen,
            MyERP then opens the same screen for the company you picked.
          </li>
          <li>
            <strong>Green band</strong>: where you are (the small links above
            the title take you back a step), the page title, key facts, and the
            page's main buttons on the right.
          </li>
          <li>
            <strong>Activity</strong> on the right: who changed what on this
            screen, and when (see "Change log").
          </li>
          <li>
            <strong>Tabs</strong> inside the band split a page into sections,
            for example a company's Overview, Branches, Licences and
            certificates, and Modules.
          </li>
        </ul>

        <h3>Saving and cancelling</h3>
        <p>
          Every form that adds or changes something has a green "Save" button.
          "Cancel" closes the form without changing anything. If something is
          missing or wrong, a red message under the form says what to fix, and
          nothing is saved until you fix it.
        </p>

        <h3>Duplicating a record</h3>
        <p>
          To make something that is much like an existing record, click
          "Duplicate" beside it (for a ledger, in its panel). The usual form
          opens already filled in, with "(copy)" after the name. Change what
          differs and click "Save": a new record is made and the original is
          left as it was. Nothing is saved until you click "Save". "Duplicate"
          is in its own column at the end of each row, after "Edit".
        </p>
        <h3>Viewing, editing and disabling</h3>
        <p>
          At the end of each row is "Edit" if your role lets you change that
          master, or "View" if you may only look. "View" opens the same form
          with everything locked and no "Save" button; "Close" shuts it. Records
          are never deleted. While you are editing a record, a "Disable" button
          (or "Enable", for one already disabled) sits beside "Save" and
          "Cancel". It asks you to confirm and then takes effect at once,
          without needing "Save". A disabled record stays on the list, greyed,
          and cannot be picked in new entries. The Head office branch cannot be
          disabled.
        </p>
        <ul>
          <li>
            Companies, branches, ledger groups, ledgers, credit terms, users and
            roles all have "Duplicate". For a ledger group it appears on groups
            under another group.
          </li>
          <li>
            Things that must be one of a kind are left blank: a company's short
            code, GSTIN, PAN, CIN and TAN; a branch's GSTIN and default ticks; a
            certificate's number and dates; a ledger's account number; a user's
            email.
          </li>
          <li>
            A duplicated ledger does not copy opening balances or bills.
            Duplicating a customer or supplier makes a new customer or supplier
            with the same GST details, addresses and contacts, and its own
            customer or vendor number.
          </li>
        </ul>

        <h3>Folding lists</h3>
        <p>
          Lists that follow a tree, like ledger groups, have an arrow before
          each row that has rows under it. Click the arrow to fold or unfold.
          "Show levels" with 1, 2, 3 … All folds the whole list to that depth in
          one click. There is no limit to how deep a tree can go; the buttons
          match the deepest level in use.
        </p>

        <h3>Dashboard</h3>
        <p>
          The "Dashboard" is the first screen after you sign in, and the first
          item in the top menu. It shows the company picked at the top right:
          how many ledgers, customers, suppliers and branches it has, and a list
          headed "Needs your attention" for things to fix, such as opening
          balances that do not balance or a licence or certificate that is
          expired or due for renewal within 90 days, or a customer's or supplier's document that has lapsed or soon will. The buttons under "Go to"
          open the company's ledgers, ledger groups, the credit terms, and the
          list of all companies. Change the company at the top right to see
          another one.
        </p>
      </>
    ),
  },
  {
    id: "companies",
    title: "Companies",
    summary:
      "Adding a company and keeping its registration details up to date.",
    body: (
      <>
        <p>
          A company is one legal entity with its own books, GST registration and
          document numbers. Open them from "Admin", then "Company", in the top
          menu (Owners only). A new company starts with a Head office branch and
          the standard ledger groups.
        </p>

        <h3>Add a company</h3>
        <p>Only an Owner can add a company.</p>
        <ol>
          <li>Go to Admin, then "Company", and click "Add company".</li>
          <li>
            Fill in the details below and tick the modules the company uses.
          </li>
          <li>Click "Save". The company's page opens.</li>
        </ol>
        <Fields
          rows={[
            ["Legal name", "The name as registered."],
            [
              "Short code",
              "Goes in front of document numbers, for example AOL. Leave it blank to use the initials. It cannot be changed later.",
            ],
            [
              "GSTIN",
              "Leave blank if the company is not registered for GST. Typing a GSTIN fills in the PAN and state.",
            ],
            ["PAN", "The company's PAN."],
            ["State", "The state of the registered office."],
            [
              "Type of entity",
              "Proprietorship, partnership, LLP, private or public limited, or one person company.",
            ],
            [
              "CIN / LLPIN",
              "Asked for companies and LLPs registered with the MCA.",
            ],
            ["Date of incorporation, TAN", "TAN is needed for deducting TDS."],
            [
              "Registered address and contact",
              "Address, PIN, phone, email and a contact person.",
            ],
            ["Financial year starts in", "Usually April."],
            [
              "Books beginning from",
              "The date your opening balances are as at. Blank means the start of the current financial year.",
            ],
            [
              "Use foreign currencies",
              "Tick for exports, imports or EEFC accounts. Ledgers can then be kept in another currency; the books stay in rupees.",
            ],
            [
              "Printing",
              'Tick "Print a small Lord Ganesha image…" to print a small image at the top centre of the first page of every printout: purchase orders, reports and all other prints. "Use our own image…" puts your own PNG or JPG (up to 300 KB) in its place; "Use the standard image" brings the standard one back. The image is saved as soon as it is chosen.',
            ],
            [
              "Mail Account",
              'The shared mailbox MyERP sends mail from (mail to suppliers, for example), shown when editing a saved company. Give the "Mailbox Address" (such as purchase@…), a "From Name" and its "App Password". For Google Workspace, sign in to that mailbox, turn on 2-Step Verification, and make an app password under Google Account › Security › App passwords; "Mail Server" smtp.gmail.com and "Port" 587 are filled in already. Click "Save", then "Send Test Mail": a test mail comes to your own address. The password is kept locked and never shown again; leave it blank to keep the saved one. Replies to mail sent from MyERP go to the person who sent it.',
            ],
          ]}
        />

        <h3>The company page</h3>
        <p>
          Click a company's name. The band shows its GSTIN, PAN and state.
          Ledgers and ledger groups are opened from "Admin", then "Company". The
          Overview tab shows:
        </p>
        <ul>
          <li>
            <strong>Opening balance difference</strong>: debit openings minus
            credit openings across all ledgers. It should be zero once every
            opening balance is in.
          </li>
          <li>
            <strong>Next renewal</strong>: the licence or certificate that
            lapses soonest.
          </li>
          <li>
            <strong>Branches</strong>: how many are open.
          </li>
          <li>Registration, address and books details.</li>
        </ul>
        <p>
          To change the details, click "Edit" in the band, make the changes and
          click "Save".
        </p>
      </>
    ),
  },
  {
    id: "branches",
    title: "Branches",
    summary:
      "Offices, factories and warehouses, and which addresses documents pick first.",
    body: (
      <>
        <p>
          A branch is any place the company works from: head office, factory,
          warehouse or shop. Every voucher will carry a branch, so reports can
          be seen branch by branch.
        </p>
        <h3>Add or change a branch</h3>
        <ol>
          <li>Open the company and click the "Branches" tab.</li>
          <li>Click "Add branch", or "Edit" on a branch.</li>
          <li>Fill in the details and click "Save".</li>
        </ol>
        <Fields
          rows={[
            ["Name", "For example Bhiwandi warehouse."],
            ["State", "Where the branch is."],
            [
              "GSTIN",
              "Only if the branch is registered separately in that state.",
            ],
            [
              "Address and contact",
              "Address, PIN, phone, email and contact person.",
            ],
            [
              "Default addresses",
              "Tick Default billing address, Default ship to or Default ship from. Each can be on only one branch; documents pick it first and you can change it on each document. To move a default, tick it on the other branch.",
            ],
            [
              "Stock",
              'Every branch can hold goods, so every branch appears under "Masters", "Warehouses", where you add its racks, bins and areas. Tick "No stock" only for a branch where goods are never stored, such as a sales-only office; it then does not appear there.',
            ],
          ]}
        />
        <p>
          To add or change many branches at once, use "Actions" at the top of
          the Branches tab (see "Import, export and print"). In the file,
          "State" is the state's name, and "Yes" in a default column moves that
          default to the branch.
        </p>
      </>
    ),
  },
  {
    id: "certificates",
    title: "Licences and certificates",
    summary:
      "FSSAI, IEC, Udyam, organic, ISO, LUT and other registrations with renewal dates.",
    body: (
      <>
        <p>
          Keep every registration that has to be renewed here, so the company
          page can show what lapses next. Types include FSSAI, Udyam, IEC,
          organic (NPOP, NOP, EU), ISO, FSSC 22000, LUT, factory licence,
          pollution consent, shop licence and Other.
        </p>
        <h3>Add a certificate</h3>
        <ol>
          <li>
            Open the company and click the "Licences and certificates" tab.
          </li>
          <li>Click "Add certificate".</li>
          <li>
            Choose the type, enter the number, who issued it, the branch (for
            licences issued per premises, or Whole company), valid from and the
            renewal date. Leave the renewal date blank if it does not lapse.
          </li>
          <li>Click "Save".</li>
        </ol>
        <Note>
          When a certificate is renewed, add the new one as a new certificate.
          The old one stays on record. Remember that the IEC must be updated
          every year.
        </Note>
        <p>
          To add or change many at once, use "Actions" at the top of the tab
          (see "Import, export and print"). In the file, "Certificate" is the
          type as in the list, and "Branch" is the branch's name, or empty for
          the whole company.
        </p>
      </>
    ),
  },
  {
    id: "credit-terms",
    title: "Credit terms",
    summary:
      "How customers pay and suppliers are paid: 30 days, full advance, 50% advance and 50% on delivery.",
    body: (
      <>
        <p>
          Credit terms are one list shared by every company in the group. Each
          customer or supplier picks one on its ledger, and sales and purchase
          documents will work out when each part of a bill is due from it. The
          list starts with the usual ones: "Full advance", "50% advance, 50% on
          delivery", "50% advance, 50% before dispatch", "On delivery", and 15,
          30, 45 and 60 days.
        </p>
        <h3>Add credit terms</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Credit terms".</li>
          <li>
            Click "Add credit terms" (it opens in a new browser tab) and give
            them a name, such as "30% advance, 70% in 15 days".
          </li>
          <li>
            Fill in one row per part: the share of the bill, when it falls "Due"
            (with the order as an advance, before dispatch, on delivery, or
            after the bill date), and any "Plus days" after that. Click "Add
            part" for another row.
          </li>
          <li>
            The shares must add up to 100%; the total under the rows turns red
            until they do. Click "Save".
          </li>
        </ol>
        <p>
          Credit terms can be changed at any time, also after customers or
          suppliers use them (their parts stay editable).
        </p>
        <p>
          The list shows each term in words and how many parties use it. Click
          a row to see its details and activity in the panels on the right;
          "Edit" and "Duplicate" open in a new browser tab, and "Save" or
          "Cancel" closes it. Credit terms are never deleted: tick "Disabled"
          in the "Switches" panel and "Save" to stop offering them to new
          parties (untick it to bring them back). Parties that already have
          them keep them.
        </p>
        <p>
          To change many at once, use "Actions" at the top of the screen. See
          the chapter "Import, export and print".
        </p>
      </>
    ),
  },
  {
    id: "terms",
    title: "Terms and conditions",
    summary: "Named sets of terms printed on purchase orders, a default for each company, and a supplier's own set.",
    body: (
      <>
        <p>
          A set of terms and conditions is the text printed at the foot of an
          order: delivery, packing, invoices, payment and so on. Each set is for
          "Purchase" or "Sales" (sales documents use them once Sales is built).
          This is one list shared by every company in the group.
        </p>
        <h3>Add a set</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Terms and conditions".</li>
          <li>
            Click "Add terms" (it opens in a new browser tab). Give it a
            "Name", such as "Purchase - tea", and a "Type".
          </li>
          <li>
            Under "Terms", write one term per line. A line ending in ":", such
            as "Invoices:", prints as a heading over the terms below it.
          </li>
          <li>
            Under "Default For", tick the companies whose new orders should
            start with this set. A company has one default set of each type:
            ticking it here takes it off its old default.
          </li>
          <li>Click "Save".</li>
        </ol>
        <h3>A supplier's own terms</h3>
        <p>
          On a supplier's ledger, pick its "Terms and Conditions" under "GST
          And Credit". Its new purchase orders then start with that set instead
          of the company's default. Leave it empty to use the default.
        </p>
        <p>
          An order keeps its own copy of the text, so changing a set later does
          not change orders already made. Sets are never deleted: tick
          "Disabled" to stop offering one. Once a set is used by a supplier, a
          company or a submitted order, its "Type" cannot change.
        </p>
      </>
    ),
  },
  {
    id: "price-lists",
    title: "Price lists",
    summary:
      "Rates for selling and buying, with start dates and lower rates for bigger quantities, and a customer's own prices.",
    body: (
      <>
        <p>
          A price list is a named set of rates for items, for selling or for
          buying. Each rate starts on a date, and an item can have a lower rate
          for bigger quantities. This is one list shared by every company in the
          group. Prices are used for rates on quotations, orders and invoices
          once Sales and Purchase are built; until then the item's own "MRP" is
          unchanged.
        </p>
        <h3>Add a price list</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Price lists".</li>
          <li>
            Click "Add price list" (it opens in a new browser tab). Give it a
            "Name", such as "Retail 2026", a "Type" ("Selling" or "Buying") and,
            if it is not rupees, the "Currency".
          </li>
          <li>
            Under "Prices" click "Add price". Pick the "Item" and one of its
            units, then fill in "From Qty" (it starts at 1), the "Rate" and the
            "From Date". For a lower rate on bigger orders, add another line for
            the same item with a bigger "From Qty".
          </li>
          <li>Click "Save".</li>
        </ol>
        <p>
          Rates are before GST, as GST is added from the item's own rate on the
          bill date. A rate is for the unit shown, so a carton has its own line;
          there is no automatic conversion between units. A new rate is a new
          line with a later date: old lines stay as history. The rate in force
          is the latest one that has started, for the biggest "From Qty" not
          above the quantity ordered. The same item, unit, quantity and date
          cannot appear twice.
        </p>
        <h3>A customer's own prices</h3>
        <p>
          When one customer pays a different rate for one item and everything
          else follows the list, give that customer its own price instead of
          changing the list:
        </p>
        <ul>
          <li>
            On the customer's ledger, pick the "Price list" under "GST And
            Credit". It shows only active "Selling" lists.
          </li>
          <li>
            Open the "Item Prices" section of the same ledger and click "Add
            price": item, unit, "From Qty", "Rate" and "From Date". Click "Save"
            on the ledger.
          </li>
          <li>
            Where a customer has any price of its own for an item, only those
            are used for that item, so add every slab that customer should get;
            for its other items the price list applies.
          </li>
          <li>
            The same lines show on the item, under "Customer Prices", where
            they can also be added, changed and removed: it is one set of data
            seen from both sides.
          </li>
        </ul>
        <h3>Suppliers' prices</h3>
        <p>
          Purchase prices work the same way. Make a price list with the type
          "Buying". On a supplier's ledger, the "Price list" box offers only
          "Buying" lists, and its "Item Prices" section holds that supplier's own
          rates (item, unit, "From Qty", "Rate", "From Date"). The item shows
          them under "Supplier Prices", listed by supplier, where they can also
          be changed. Customer and supplier prices are kept apart, so a firm
          that is both has separate sale and purchase rates. When you
          "Duplicate" an item, "Copy supplier prices" under "Supplier Prices"
          is ticked: it copies every line with its quantity slabs and dates
          (untick it to start with none). Customer prices are not copied.
        </p>
        <p>
          The list shows the type, currency, how many prices it has and how
          many customers and suppliers use it. Click a row to see its details and activity on
          the right; "Edit" and "Duplicate" open in a new browser tab. A price
          list is never deleted: tick "Disabled" in the "Switches" panel and
          "Save" to stop offering it. Once customers use a list, its "Type" and
          "Currency" cannot change. To add or change many prices at once, use
          "Actions" at the top of the screen (see "Import, export and print").
        </p>
      </>
    ),
  },
  {
    id: "items",
    title: "Items",
    summary:
      "The catalogue of products, materials and services, each with its units, sizes, weights and barcodes.",
    body: (
      <>
        <p>
          Items are one catalogue shared by every company in the group. Each
          item gets a number such as ITEM-00001. The list shows the item
          number, name, group, HSN, stock unit and today's GST rate. Click an
          item and its "Item Details" and "Activity" (the change log) show in
          the panels on the right, with "View", "Edit" and "Duplicate" buttons under "Item Details". Type in the search box to find an item by
          name, number, HSN or barcode.
        </p>
        <p>
          Double-click an item, press Enter, or click "View" under "Item Details" to see its own
          page, which opens in a new browser tab so the list stays open. It has folding sections: "General", "Sales", "Purchase", "GST
          Rates", "Stock And Quality", "Units Of Measure", "Customer And Supplier
          Names" and "Connections". Click a section's title bar to open or close it; a closed section
          still shows a line of its main values. "Switches" and "Activity" are
          in the panels on the right. People who may change items also see
          "Edit" and "Duplicate" in the green bar; "Close" shuts the tab.
        </p>
        <p>
          "Add item", "Edit" and "Duplicate" also open the form in a new browser tab
          with the whole width, so the list stays open in the first tab.
          "Save" or "Cancel" closes the new tab and the list refreshes and
          selects the item. If you opened the form link by hand, the tab cannot
          close itself and shows the list instead.
        </p>
        <h3>Add an item</h3>
        <ol>
          <li>
            Click "Masters" in the top menu, then "Items", then "Add item". The
            page is titled "Add item" ("Edit item" when you change one) and has
            "Cancel" and "Save" in the green bar. Below the item name are
            folding sections: "General", "Sales", "Purchase", "GST Rates",
            "Stock and quality", "Units of measure", "Customer and supplier names" and
            "Connections" (empty for now: it will list the documents that use
            the item). Click a
            section's title bar to open it; one section is open at a time and a
            closed one still shows a line of its main values.
          </li>
          <li>
            The large "Item name" at the top is a box you can click and change at
            any time; the "Item number" beside it is given when you save. Fields
            marked with a red * must be filled in. Under "General", choose
            "Goods or service", pick the "Item group"
            (it must be filled in; see the chapter "Item groups"), pick the "HSN code" from the list (it must be filled in, and a code that is not in the list is refused; its "HSN description" shows beside it; for a service use its SAC code),
            the "Default unit of measure" (the unit stock is counted in, such as
            Packet) and the "Brand" (it must be filled in; see the chapter "Brands"). In the "Switches" panel on the right, tick "Disabled" to stop using the item, and untick "Allow
            purchase" or "Allow sales" where the item is not bought or sold. Tick "Offer to all" to offer the item to every customer and supplier even when theirs has a Products list.
            "Maintain stock" is separate from goods or service: untick it for an
            item whose stock is not to be kept, and tick it for a service whose
            stock is. For a service that keeps stock (job work, where the
            customer's goods are processed and sent back), two more boxes
            appear: "Delivery HSN code" and its description. Pick the HSN code
            of the goods there; it goes on the delivery challan and e-way
            bill, while the "HSN code" above (the service code) goes on the
            invoice and e-invoice. The boxes disappear when the item is goods
            or does not keep stock. "Notes" are in the box below.
            For a service, "Use as Purchase Charge" in the "Switches" panel
            offers it under "Charges" on a purchase order (freight, packing,
            insurance and the like), and "Add to Stock Cost" ("No", "By
            Quantity" or "By Value") is how it is spread into the cost of the
            goods unless changed on the order.
          </li>
          <li>
            On the "Sales" tab, write the "Sales description" customers should
            see on quotations, orders and bills (both descriptions are plain
            text; on a printed document they show a little smaller, under the
            item name in bold), and pick the "Default sales
            unit" (for example Carton). Fill in the "MRP (₹)", the "USP" and the
            "Batch No" printed on the pack. "Best before" is a number with
            "Days" or "Months": a manufacturing order adds it to the
            manufacturing date to work out the best-before date. On the
            "Purchase" tab write the "Purchase description" for suppliers (a
            purchase order line starts with it and can change it), pick
            the "Default purchase unit", and fill in the "Lead time in days",
            "Safety stock qty", "Minimum order qty" and "Max stock qty" (the
            quantities are in the item's default unit; the maximum cannot be
            below the safety stock). The default units are picked from the
            item's own units, so add a unit on the "Units of measure" tab
            first. Left blank, the stock unit is used.
          </li>
          <li>
            In the "GST Rates" section, click "Add rate", fill in "From" (the
            date the rate starts) and choose the "GST Rate (%)" from the
            dropdown. The dropdown lists the rates kept centrally by MyERP (0,
            0.25, 3, 5, 18 and so on), so a rate cannot be mistyped; a rate
            that is not in the list cannot be saved. When the law changes, do
            not change the old row: click "Add rate" again and give the new rate
            with its start date. A bill takes the rate in force on the bill
            date, and the item's details mark today's rate "In force".
          </li>
          <li>
            On the "Stock and quality" tab, choose the "Default material request
            type": "Manufacture" if the item is made in-house, "Purchase" if it
            is bought, or "Customer Provided" if the customer supplies it (it is
            what a material request for the item starts as, and can be left
            "Not set"). In the "Switches" box tick "Track batches"
            if you must follow batch numbers, and tick "Quality check on
            receipt" if goods must be checked when they arrive. On every tab a
            red * marks a field that must be filled in.
          </li>
          <li>
            In the "Units Of Measure" section, each unit the item is bought,
            sold or moved in is one line, with "Edit" (and "Remove") on its
            right. The stock unit is added for you. Click "Add unit" for each
            other unit, or "Edit" to change one: a box opens under the lines.
            For a Carton, say it contains 4 of "Inner box", and for an Inner box
            that it contains 6 of "Packet"; the "= Packet" column then shows 24
            by itself. Fill in the length, breadth and height in centimetres,
            the net and gross weight in kilograms, and the barcode. Volume is
            worked out from the size. Under "Used for", tick where each unit is
            the usual one. Click "Done" to put the unit back as a line, or
            "Cancel" to leave it as it was. Nothing is saved on the item until
            you click "Save" at the top.
          </li>
          <li>
            If a customer or supplier calls the item by its own name or code,
            open "Customer And Supplier Names", type the party in "Add Customer
            Or Supplier", pick it, and fill in "Their Item Name", "Their Item
            Code" or both. Click "Remove" on a row to take it off.
          </li>
          <li>Click "Save".</li>
        </ol>
        <Note>
          A party's item code can belong to only one item, so a code from a
          scanned e-invoice always finds one item. A party appears once on an
          item, and each row needs a name, a code or both. A duplicate starts
          with no customer or supplier names. A missing size is only a reminder under the table, not an error, so
          you can add an item before it has been measured. "Whole numbers only"
          on a unit (for example cartons) will stop a quantity such as 2.5 on
          documents. A barcode can belong to one item only.
        </Note>
        <p>
          Items are never deleted: click "Edit", tick "Disabled" and "Save" to
          stop using one (untick it to bring it back). Use "Duplicate" to start
          a new item from an existing one; barcodes are not copied, and under
          "Supplier Prices" the box "Copy supplier prices" is ticked to copy the
          supplier prices as well (see "Price lists").
        </p>
        <p>
          Once an item is in use (entries such as stock or orders are against
          it), a line at the top of its form says what uses it, and its key
          fields are greyed with a "Locked" tag and cannot be changed: "Goods or
          service", "HSN code", "Delivery HSN code", "Default unit of measure",
          "Maintain stock", "Track batches" and the units of measure. Its
          "Item group" can still be changed, but only to another group under
          the same top-level group. The name, notes and everything else stay
          open, and you can still tick "Disabled". Items made before the brand
          became required are counted under "Needs your attention" on the
          Dashboard; the next time one is saved, pick its brand.
        </p>
        <p>
          To change many at once, use "Actions" at the top of the screen. See
          the chapter "Import, export and print".
        </p>
      </>
    ),
  },
  {
    id: "hsn",
    title: "HSN codes",
    summary:
      "The central list of HSN and SAC codes that the item form searches as you type.",
    body: (
      <>
        <p>
          MyERP keeps one list of HSN and SAC codes for everyone, so it is the
          same in every company and is looked after centrally. You cannot change
          it, but you can search it: click "Masters" in the top menu, then "HSN
          codes", and type a few digits of the code or words from the
          description. Click a code in the list to see its details on the
          right.
        </p>
        <p>
          On the item form, the "HSN" box searches this list as you type. Type a
          few digits, or words such as "turmeric", and click the code you want.
          A code that is not in the list is refused. If a code you
          need is missing, click "Request Addition" (see below).
        </p>
        <h3>Ask for a missing code or GST rate</h3>
        <p>
          Click "Request Addition" at the top of the "HSN codes" screen, or the
          "Not in the list? Request Addition" link under the "HSN code" box on
          the item form (the "GST Rates" section has one too). A new tab opens:
          pick the "List" ("HSN or SAC code", "GST rate", "Country" or "PIN code"),
          type the code or rate, the "Description" for an HSN code, the
          "2-Letter Country Code" for a country, the "City" and "State" for a PIN, and a "Note For The MyERP Team" if
          you like, then click "Send Request". The same entry cannot be asked for
          twice while a request for it is open, and an entry that is already in
          the list is refused.
        </p>
        <p>
          Your requests are listed under "My Requests" on that screen with their
          status ("Open", "Added to the list" or "Not needed"). When the team
          decides, a line appears under "Needs your attention" on your Dashboard;
          click "OK" to dismiss it. An added entry is in the list at once, for
          every company.
        </p>
      </>
    ),
  },
  {
    id: "places",
    title: "Countries and PIN codes",
    summary:
      "The central lists of countries, and of PIN codes with their city and state.",
    body: (
      <>
        <p>
          MyERP keeps one list of countries and one of PIN codes for everyone,
          so they are the same in every company. You cannot change them, but
          you can search them: click "Masters" in the top menu, then
          "Countries" or "PIN codes", and type in the search box. Click a line
          to see its details on the right; for a PIN code that includes the
          couriers that deliver there.
        </p>
        <p>
          A customer or supplier's "Country" is picked from the country list
          (it starts at India). The PIN code list gives an Indian address its
          city and state: see the chapter "Ledgers".
        </p>
        <h3>Ask for a missing country or PIN code</h3>
        <p>
          Click "Request Addition" at the top of either screen, or the "PIN not
          in the list? Request Addition" link under the "PIN code" box on an
          address. Pick the "List", fill in the boxes and click "Send Request".
          Once the MyERP team clicks "Approve &amp; Add", the entry is in the
          list for every company, and a line on your Dashboard tells you.
        </p>
      </>
    ),
  },
  {
    id: "central",
    title: "Central tables",
    summary:
      "For MyERP platform admins: the lists kept once for every customer.",
    body: (
      <>
        <p>
          Some lists are the same for everyone, so MyERP keeps them once in a
          central place instead of in each customer's books: the HSN codes,
          states, countries, PIN codes and which courier delivers to which PIN
          code. Only platform admins, whose sign-in emails MyERP has been told
          about, see "Central" in the top menu. A customer's Owner does not.
        </p>
        <p>
          The screen has four tabs. "Customers" lists every customer group
          (tenant) with its status. "Shared lists" shows each central list with
          the number of rows in it (click "Open" to look inside) and the "Load
          lists from a file" box. "GST Rates" holds the rates every customer's
          items choose from: type a rate under "GST Rate (%)" and click "Add
          rate", or click "Disable" to stop offering a rate for new entries
          (items that already use it keep it; rates are never deleted).
          "Couriers" holds the courier list and the requests customers have
          sent.
        </p>
        <h3>Add a customer</h3>
        <ol>
          <li>Click "Central" in the top menu, then the "Customers" tab.</li>
          <li>In the "Add customer" box click "Add customer".</li>
          <li>
            Give the "Customer name", the "Short name (web address)", the
            "Owner's sign-in email" and the "Owner's name", then click "Save".
            Creating the customer's own database can take half a minute.
          </li>
        </ol>
        <p>
          The Owner can then sign in with the Google account for that email
          address and set up the companies.
        </p>
        <h3>Load HSN codes or a courier's PIN codes</h3>
        <p>
          The "Load lists from a file" box fills the central lists from a file.
          For HSN and SAC codes, click "Choose file" under "HSN and SAC codes"
          and pick an Excel or CSV file with the code in the first column and
          the description in the second (every sheet of an Excel file is read).
          For a courier's PIN codes, first pick the courier in the box under
          "PIN codes and a courier's coverage", then choose its serviceability
          CSV.
        </p>
        <p>
          A window opens and checks the file first: it says "Checking the
          file…" while it works, and nothing is saved yet. It then shows how
          many codes are new, changed or already there, and lists every row with
          a problem at one time, such as a code that is not 2, 4, 6 or 8 digits
          or a row with no description. Click "Load" (or "Load the rest" when
          there are problems, which leaves those rows out) to save, or "Cancel"
          to stop. A last message says what was loaded. When rows were left out, click
          "Download the left-out rows (Excel)": the file has the same columns
          plus "Why it was left out", so you can correct those rows and load
          the file again. The good rows are already in.
        </p>
        <h3>Add a courier</h3>
        <p>
          The "Couriers" box lists the couriers, aggregators and transporters
          that every customer can pick on a transporter. Customers cannot add to
          it: a courier is added here once MyERP can look it up, such as one
          whose API can be arranged, and then every customer sees it.
        </p>
        <ol>
          <li>Click "Central" in the top menu and find the "Couriers" box.</li>
          <li>Click "Add courier" and fill in the "Name" and "Kind".</li>
          <li>
            Fill in "Tracking number looks like" in words, and the "Tracking
            page" with {"{awb}"} where the tracking number goes, so that
            shipments get a "Track" link. "Tracking number pattern" is optional:
            a regular expression that a tracking number must match.
          </li>
          <li>
            Set "Integration" to "Tracking only" or "Booking and tracking" when
            customers can connect their own login with the courier. Under
            "Credentials The Customer Supplies", click "Add credential" for each
            thing a customer must enter, such as "Client ID" or "API Key", and
            tick "Secret" for passwords and keys.
          </li>
          <li>Click "Save".</li>
        </ol>
        <p>
          Couriers are never deleted: click "Edit" and then "Disable" to stop
          offering one; transporters already using it keep it.
        </p>
        <h3>Requests for HSN codes and GST rates</h3>
        <p>
          Click "Central" in the top menu, then the "Requests" tab. Each line is
          an HSN or SAC code or a GST rate a customer asked for, with the
          customer, who asked, and their note. Click "Approve &amp; Add" to put
          the entry in its list for every company; the customer is shown a
          notice on their Dashboard. Click "Not needed" to decline it (they are
          told that too), or "Reopen" to bring a closed request back.
        </p>
        <h3>Courier requests</h3>
        <p>
          When someone saves a transporter with "Not in the list", it appears in
          the "Courier requests" box with the customer, the GSTIN and the note
          they wrote. If MyERP can look the courier up, add it in the "Couriers"
          box and click "Mark as added"; click "Not needed" to set a request
          aside, or "Reopen" to bring it back.
        </p>
      </>
    ),
  },
  {
    id: "reset",
    title: "Reset data",
    summary:
      "For Owners: clear a company, or the whole group, back to a clean start.",
    body: (
      <>
        <p>
          This is for staging and trial runs, to start again without setting
          everything up from scratch. It is switched off on live books, and only
          an Owner sees it: click "Admin" in the top menu, then "Reset data".
        </p>
        <h3>The three levels</h3>
        <ul>
          <li>
            <strong>Entries only</strong>: vouchers and stock entries are
            removed. Masters and opening balances stay.
          </li>
          <li>
            <strong>Entries and the masters added to this company</strong>: also
            removes the company's ledgers (with their opening balances), its own
            ledger groups, branches other than the head office, licences and
            certificates, and customers or suppliers no other company uses. The
            standard groups, the head office and the Cash ledger stay.
          </li>
          <li>
            <strong>Whole group back to blank</strong>: every company is cleared
            as above, and the shared items, the credit terms and units you
            added, and the running numbers start again. Companies, users and
            roles stay.
          </li>
        </ul>
        <h3>Clear data</h3>
        <ol>
          <li>
            Choose the "Level" and, for the first two, the "Company". The list
            under "This will remove" shows what will go.
          </li>
          <li>
            Under "Confirm", type the company name exactly (or RESET ALL DATA
            for the whole group).
          </li>
          <li>Click "Reset data" and confirm.</li>
        </ol>
        <Note>
          A backup file of everything removed is saved to your computer the
          moment the reset is done. Keep it: it is the only way to get the data
          back. The reset is also written to the company's "Activity".
        </Note>
      </>
    ),
  },
  {
    id: "batches",
    title: "Batches",
    summary:
      "The batches (lots) of batch-tracked items, with their mfg and expiry dates and quality status.",
    body: (
      <>
        <p>
          An item keeps batches when "Track batches" is ticked on its form.
          Each batch belongs to one item, and its "Batch No" only has to be
          different from the other batches of that item: two different items
          may both have batch 1234. Batches are shared by every company in the
          group, like items.
        </p>
        <h3>Add a batch</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Batches".</li>
          <li>
            Click "Add batch". The form opens in a new browser tab. Pick the
            "Item" (only items that track batches are listed) and give the
            "Batch No". If you like, add the "Supplier's Batch No", "Mfg Date",
            "Expiry" and "Notes".
          </li>
          <li>
            Leave "Expiry" blank to have it worked out: the mfg date plus the
            item's "Best before" period.
          </li>
          <li>
            "Status" is "Released" (free to use), "Quarantine" (held for a
            quality check) or "Rejected".
          </li>
          <li>Click "Save"; the tab closes and the batch is selected in the list.</li>
        </ol>
        <p>
          A goods receipt will also make a new batch from its line as goods are
          received. Pick an item in the box above the list to see only its
          batches. Click a batch to see its details and activity on the right;
          "Edit" (or a double-click) and "Duplicate" open in a new tab. Once a
          batch is used in an entry its item can no longer change. Batches are
          never deleted: tick "Disabled" under "Switches" instead. To change
          many batches at once, use "Actions" (see "Import, export and print").
        </p>
      </>
    ),
  },
  {
    id: "brands",
    title: "Brands",
    summary:
      "The brand names that items are sold under, picked on the item form.",
    body: (
      <>
        <p>
          Brands are one list shared by every company in the group. An item
          picks its brand in the "Brand" box on the General tab of the item form
          (click the box and type a few letters to narrow the list).
        </p>
        <h3>Add a brand</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Brands".</li>
          <li>
            Click "Add brand". The form opens in a new browser tab. Give the
            "Name" (for example Apurvam) and, if you like, "Notes".
          </li>
          <li>
            Click "Save"; the tab closes and the brand is selected in the list.
          </li>
        </ol>
        <p>
          Click a brand in the list to see its details on the right, with its
          activity below. "Edit" (or a double-click on the row) and "Duplicate"
          open in a new tab. Brand names must be different, whatever the
          capital letters. The "Items" column shows how many items carry each
          brand. Brands are never deleted: on the form, tick "Disabled" under
          "Switches" to stop offering a brand, and untick it to bring it back;
          items already using it keep it. To
          change many brands at once, use "Actions" at the top of the screen
          (see "Import, export and print").
        </p>
      </>
    ),
  },
  {
    id: "item-groups",
    title: "Item groups",
    summary:
      "The tree of groups and sub-groups that items sit in, such as Raw material > Spices.",
    body: (
      <>
        <p>
          Item groups are one tree shared by every company in the group, built
          the same way as ledger groups. Each item sits in one group, which you
          pick in the "Item group" box on the item form (it must be filled in; click
          the box and type a few letters). Only a group with no sub-groups is offered there, so
          an item always sits in the lowest group, such as "Whole spices" and
          not "Spices". A group that already has items cannot be given a
          sub-group until its items are moved to another group.
        </p>
        <h3>Add a group</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Item groups".</li>
          <li>
            Click "Add group" for a main group, or click "+ Sub-group" beside a
            group to add one under it. The form opens in a new browser tab.
            Give the "Name" (for example Whole spices) and, if you like,
            "Notes".
          </li>
          <li>
            To place a group elsewhere, change the "Under" box. A group cannot
            go under itself or a group below it.
          </li>
          <li>Click "Save"; the tab closes and the group is selected in the list.</li>
        </ol>
        <p>
          The arrow beside a group folds or opens the groups under it, and "Show
          levels" opens the tree to the depth you pick. The "Items" column
          counts the items in a group and in the groups below it; click the number to
          see those items in the Items list (the "Item group" box above the list
          shows which group is chosen; pick "All groups" to see every item). Click a group
          to see its details on the right, with its activity below. "Edit",
          "Duplicate" and "+ Sub-group" each open in a new tab.
        </p>
        <p>
          Once an item sits in a group, or in a group below it, that group
          can be moved only under another group of the same main group, so
          reports keep their meaning; the form shows a line "In use: ..." at the
          top and offers only those groups in "Under". Names and notes can
          still be changed. Names must be different whatever
          the capital letters. Groups are never deleted: on the form, tick "Disabled" under
          "Switches" to stop offering a group, and untick it to bring it back;
          items already in it keep it. To change many groups at once, use
          "Actions" (see "Import, export and print"); in an import file, list a
          group before the groups under it.
        </p>
        <h3>Accounts of a main group</h3>
        <p>
          The accounts that the items of a group post to are set once, on the
          main group, and every group and item under it uses them. Open a
          main group and fill the "Accounts" box: there is one row for each
          company, with two ledgers to pick (click the box and type a few
          letters). "Stock Ledger" holds the value of the stock on hand and
          lists the ledgers under Stock-in-Hand. "COGS/Expense Ledger" takes
          the cost of stock goods when they are sold, of stock used inside the
          company or written off, and of items that keep no stock, such as
          stationery or a service; it lists expense ledgers. Leave a company empty
          if it does not use the group. A group under a main group shows the
          same accounts read only, with a link to open the main group. The
          "Accounts" panel on the right of the list shows them too.
        </p>
        <p>
          Once any stock entry or purchase is posted against a company's
          accounts, that company's row is greyed with the tag "Locked" and the
          reason; the other companies' rows stay open.
        </p>
      </>
    ),
  },
  {
    id: "units",
    title: "Units",
    summary:
      "The list of units of measure (Packet, Carton, Kilogram) that items will use.",
    body: (
      <>
        <p>
          Units are one list shared by every company in the group. Items will
          pick their units from it. The list starts with the usual ones: Nos,
          Packet, Inner box, Carton, Pallet, Bag, Bottle, Kilogram, Gram, Tonne,
          Litre, Millilitre and Metre.
        </p>
        <h3>Add a unit</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "Units".</li>
          <li>
            Click "Add unit". The form opens in a new browser tab. Give the
            "Name" (for example Drum) and a "Short name" (for example drm).
          </li>
          <li>
            Pick the "GST unit code" (click the box and type a few letters to
            narrow the list). This is the official code GST returns use for the
            unit (for example CTN for carton, KGS for kilogram). If none fits,
            pick OTH (Others), as the starting "Pallet" does.
          </li>
          <li>
            Tick "Whole numbers only" for units that cannot be split, such as
            cartons: a quantity like 2.5 cartons will then be refused on
            documents.
          </li>
          <li>
            Click "Save"; the tab closes and the unit is selected in the list.
          </li>
        </ol>
        <p>
          Click a unit in the list to see its details on the right, with its
          activity below. "Edit" (or a double-click on the row) and "Duplicate"
          open in a new tab.
        </p>
        <p>
          Once an item uses a unit, its "GST unit code" and "Whole numbers only"
          cannot be changed, so old records keep their meaning: the form shows
          a line "In use: ..." at the top and greys those two fields with a
          "Locked" tag. The name can still be corrected.
        </p>
        <p>
          Wherever a unit is picked or shown in the masters, such as on an item,
          it reads with its short name in brackets, for example "Kilogram (Kg)".
          Entry screens and reports will show the short name alone ("Kg").
          Names and short names must be different from each other, whatever the
          capital letters. Units are never deleted: on the form, tick "Disabled" under
          "Switches" to stop offering a unit, and untick it to bring it back.
          Items that already use it keep it.
        </p>
        <p>
          To change many units at once, use "Actions" at the top of the screen.
          See the chapter "Import, export and print".
        </p>
      </>
    ),
  },
  {
    id: "import-export",
    title: "Import, export and print",
    summary:
      "Download a master list to Excel, fill or correct it, bring it back in, or print it.",
    body: (
      <>
        <p>
          Every list screen has an "Actions" button at the top right. Click it
          for a short list: "Print" and "Download PDF" on every list, and on
          masters also "Import from Excel…" and "Export to Excel". They work the
          same way everywhere. Import and export are on "Units", "Credit terms",
          "Items", "Item groups", "Brands", "Ledgers", "Ledger groups",
          "Branches", "Licences and certificates" and "Transporters".
          "Companies" has "Print" and "Download PDF" only: add a company with
          "Add company". The columns are always the fields of that master's
          form, so when a field is added to the form it appears in the file too.
        </p>
        <h3>Export to Excel</h3>
        <p>
          Click "Actions" and then "Export to Excel" to download the whole list
          as an Excel file (.xlsx). The first column, "ID", is MyERP's own
          number for each record. The second sheet, "How to fill", lists every
          column, whether it must be filled, and what may be written in it (for
          example the GST unit codes, or Yes and No).
        </p>
        <h3>Rows inside a record</h3>
        <p>
          Some masters keep a small table inside each record: the parts of a
          credit term, or an item's "Units of measure" and "GST rates". These
          come out on sheets of their own, named as on the form ("Parts", "Units
          of measure", "GST rates"). Each row's first column says which record
          it belongs to, by name (for example the item's name), or by its ID.
          Other masters are written by name too: write "Carton" or "ctn" for a
          unit, and "On delivery" for when a part is due.
        </p>
        <p>
          On import, a record listed on the first sheet gets exactly the rows
          listed for it on these sheets, so add, change or delete rows there as
          you would on the form. To leave them as they are, delete the whole
          sheet from the file. CSV files hold only the first sheet, so they
          never change these rows.
        </p>
        <h3>Ledgers</h3>
        <p>
          Ledgers belong to one company, so "Actions" on the Ledgers screen work
          on the company you are working in (picked at the top right). "Under
          group" is the group's name in that company. Customers and suppliers
          are ledgers too: their details ("GST type", "GSTIN", "State", "Credit
          terms", "Salesman or purchaser" and so on) are columns on the same
          sheet, left empty for other ledgers such as cash or expenses. Their
          "Opening bills", "Addresses" and "Contacts" have sheets of their own,
          each row starting with the ledger's name. Opening balances must add up
          with their bills, as on the form.
        </p>
        <p>
          A customer or supplier that another company of the group already has
          cannot be added by import: open "Add ledger" and pick it under
          "Existing customer or supplier", so both companies share one record.
        </p>
        <h3>Print and Download PDF</h3>
        <p>
          "Print" prints the list as a plain columnar report: the screen's
          title, the company (or group) and today's date at the top, then the
          list with its column headings. Your browser's print window opens; pick
          a printer. "Download PDF" saves the same report as a PDF file, ready
          to email: landscape A4, column headings repeated on every page,
          amounts on the right in Indian style (1,23,456.00), and "Page 1 of 3"
          at the foot of each page. When a company has "Printing" ticked on its
          setup, the first page carries the small Lord Ganesha image at the top
          centre.
        </p>
        <p>
          On a master the report leaves out the ID and any column that is empty
          in every row; on Ledgers it shows the main columns only (name, group,
          opening balance, currency, customer and supplier numbers, GST details,
          credit terms, active). On "Ledger groups" and on other lists (Users,
          Roles, Companies, Shipments, HSN codes) the report is the table on the
          screen: what you have searched for, picked or unfolded is what prints.
          Buttons such as "Edit" and "Duplicate" are left out.
        </p>
        <h3>Import</h3>
        <ol>
          <li>
            Click "Actions", then "Export to Excel" (to change records you
            have), or "Import from Excel…" and then "blank template" (to add new
            ones).
          </li>
          <li>
            Fill or change the rows in Excel. Keep the "ID" to change that
            record. Leave "ID" empty on a row to add a new record. Keep the
            column names in the first row as they are; you may delete columns
            you do not want to touch, and those fields stay as they are.
          </li>
          <li>Save the file as Excel (.xlsx) or CSV.</li>
          <li>
            Click "Actions" and "Import from Excel…", pick the file under "File
            to import" and click "Check file". MyERP checks every row the way
            the form would, and saves nothing yet.
          </li>
          <li>
            If any row has a problem, a table shows the sheet, the row number
            (as in Excel) and what is wrong, for example 'Name: There is already
            a unit with the name "Carton".' Fix those rows and click "Check
            file" again.
          </li>
          <li>
            When every row is right, it shows how many rows are new, changed or
            with no change. Click "Import" to save them.
          </li>
        </ol>
        <Note>
          An import saves every row or none. If even one row is wrong, nothing
          is saved, so the list is never left half changed. Each saved record
          shows in "Activity" like a change made on the form, under your name.
          Rules that protect masters in use (for example a unit's "GST unit
          code" once items use it) apply to imports too.
        </Note>
        <p>
          Anyone who can see a list can print it or download its PDF, and anyone
          who can see a master can export it. Importing needs two permissions:
          "Create and edit" and "Import from a file" under Masters. Only the
          Owner has "Import from a file" to start with; tick it on the "User
          roles" screen for any other role that should import. Up to 5,000 rows
          and 5 MB at a time.
        </p>
      </>
    ),
  },
  {
    id: "warehouses",
    title: "Warehouses",
    summary: "A warehouse's racks, bins and areas.",
    body: (
      <>
        <p>
          A warehouse is a branch of the company: every branch holds goods
          unless it is ticked "No stock". Inside it there are
          racks, a rack holds bins, and a bin is a physical location where stock
          is kept. Apart from the bins, the warehouse has areas, which are named
          zones such as Receiving, Production and Despatch.
        </p>
        <h3>The default store</h3>
        <p>
          Goods need a place even in a simple office with no racks or bins, so
          every branch that holds stock has an area called "[Branch name]
          Store", marked "Default". You can rename it, but not disable it. Goods
          that come in go to the branch's "Receiving" area if it has one,
          otherwise to the default store; you can choose another place on the
          entry.
        </p>
        <h3>Say that a branch holds no stock</h3>
        <ol>
          <li>Open the company and click the "Branches" tab.</li>
          <li>Click "Edit" on the branch.</li>
          <li>Under "Stock", tick "No stock" and click "Save".</li>
        </ol>
        <p>
          The branch then shows "no stock" in the list and leaves the
          "Warehouses" screen. Untick it to bring it back with its default
          store.
        </p>
        <h3>Add racks, bins and areas</h3>
        <ol>
          <li>
            Pick the company at the top right, then click "Masters" in the top
            menu, then "Warehouses". Each warehouse has its own box.
          </li>
          <li>
            Click "Add rack". The form opens in a new browser tab. Give the rack
            a name, for example R1, then click "Save"; the tab closes and the
            rack is selected in the list.
          </li>
          <li>
            Click "Add bin" beside the rack and give the bin a name, for example
            A1, then click "Save".
          </li>
          <li>
            Click "Add area", give it a name such as Despatch bay and pick what
            it is used for in "Used for" (Receiving, Storage, Production,
            Quality check, Quarantine, Packing, Despatch or Other), then click
            "Save".
          </li>
        </ol>
        <p>
          Names cannot repeat: a warehouse has one rack of each name, a rack has
          one bin of each name, and a warehouse has one area of each name. Use
          the arrow beside a rack to fold or show its bins. Click a rack, bin or
          area to see its details on the right, with its activity below; "Edit"
          (or a double-click) opens it in a new tab. Racks, bins and areas are
          never deleted: on the form, tick "Disabled" under "Switches", and
          untick it to bring one back. A rack can be disabled only after its
          bins are disabled. A branch that has racks,
          bins or areas besides its default store cannot be ticked "No stock". To add many at once, use "Actions" at
          the top of the "Warehouses" screen (see "Import, export and print"); in the
          file a bin names its rack in "On rack", and a rack must come before
          the bins on it.
        </p>
      </>
    ),
  },
  {
    id: "numbering",
    title: "Numbering",
    summary: "How customers, items and documents get their numbers.",
    body: (
      <>
        <p>
          The "Numbering" tab of a company shows two things: the numbers of
          masters, which are the same for every company, and the document series
          of this company.
        </p>
        <h3>Master numbers</h3>
        <p>
          Customer numbers, supplier numbers and item numbers (for example
          CUST-00001) each have a prefix and a number of digits. Click "Edit" to
          change the prefix or digits, which applies to numbers made from then
          on, or to raise the "Last number used" so that new numbers carry on
          from your old system. It can only go up.
        </p>
        <h3>Document series</h3>
        <p>
          Every kind of document (sales invoice, purchase order, payment and so
          on) has a series of its own, shown with what a number looks like, for
          example AO/SI/2627/00001: the company's short code, the document, the
          fiscal year (2627 is 2026-27) and a number of five digits. In the
          prefix, {"{YY}"} stands for the fiscal year as 2627 and
          {"{FY}"} as 2026-27; every fiscal year counts again from 00001. A
          company with a long short code gets fewer digits on invoices so that
          the number stays within 16 characters. Click "Edit" to change the
          prefix and "Digits". A sales invoice, credit note or debit note number
          can be at most 16 characters of letters, digits, / and -, as GST
          requires. No two series of a company can share a prefix. Once a number
          has been given from a series, its prefix and digits can no longer
          change.
        </p>
        <h3>A series for one branch</h3>
        <p>
          Click "Add branch series", pick the "Document" and the "Branch", give
          a prefix different from the others, and click "Save". That branch then
          numbers that document in its own series; other branches use the
          company's.
        </p>
        <h3>Carrying on from old numbers</h3>
        <p>
          Click "Years" beside a series to see the last number used in each
          fiscal year. Click "Set last number" and enter the last number your
          old system used, then "Save", and new documents carry on after it. The
          number can only go up. To change many series at once, use "Actions" at
          the top of the tab (see "Import, export and print").
        </p>
      </>
    ),
  },
  {
    id: "fiscal-years",
    title: "Fiscal years",
    summary:
      "A company's financial years and their months, and locking a closed month.",
    body: (
      <>
        <p>
          Each company has its own financial years. A year runs in whole months
          and is split into monthly periods. New companies start with the years
          from the one their books begin in up to the current one, using the
          "Financial year starts in" month of the company.
        </p>
        <h3>Add a year</h3>
        <ol>
          <li>Open the company and click the "Fiscal years" tab.</li>
          <li>
            Click "Add year". The dates offered are the year after the last one.
            A year starts on the 1st of a month, ends on the last day of a
            month, and can be up to 18 months long (a first year may be longer
            than twelve months). Years of one company cannot overlap. Leave
            "Name" empty to get a name like 2026-27.
          </li>
          <li>Click "Save".</li>
        </ol>
        <h3>Lock a month</h3>
        <p>
          Click "Months" beside a year, then "Lock" beside a month that is
          closed: nothing can be entered into a locked month. Only an Owner can
          click "Unlock" to open it again. Every lock and unlock is written to
          the "Activity" column. The dates of a year cannot be changed while any
          of its months is locked. Years are never deleted: click "Edit" and
          then "Disable" to stop using one.
        </p>
      </>
    ),
  },
  {
    id: "modules",
    title: "Modules",
    summary: "Choosing which parts of MyERP a company uses.",
    body: (
      <>
        <p>
          Not every company needs every module; a trading company may not use
          Production. The "Modules" tab lists each module, what it covers, what
          it needs, and whether this company uses it. Screens for modules that
          are not used stay hidden for that company. Accounts is always on.
        </p>
        <h3>Change the modules</h3>
        <p>Only an Owner can do this.</p>
        <ol>
          <li>Open the company and click the "Modules" tab.</li>
          <li>Click "Choose modules", tick or untick, and click "Save".</li>
        </ol>
        <p>
          Some modules need others: Production and Quality need Stock. Ticking a
          module also ticks what it needs, and unticking Stock also unticks the
          modules that need it.
        </p>
      </>
    ),
  },
  {
    id: "ledger-groups",
    title: "Ledger groups",
    summary: "The tree that ledgers sit in, following Schedule III.",
    body: (
      <>
        <p>
          Every ledger sits in a group, and groups sit under other groups, as
          deep as you need. The standard groups come with MyERP and follow
          Schedule III of the Companies Act, so the balance sheet and profit and
          loss come out in the right form. Their familiar names are kept, with
          the Schedule III head shown in small print under each name.
        </p>
        <p>
          Open them from "Masters" › "Ledger groups". The table shows each
          group's nature (asset, liability, income or expense), its Schedule III
          head and how many ledgers it holds. Click a group's ledger count to
          see those ledgers. Click a group's row to see its details (name, the
          group it sits under, nature, Schedule III head, ledgers and whether it
          is disabled) and its activity in the panels on the right. "+ Sub-group",
          "Edit" and "Duplicate" open the form in a new browser
          tab, so the tree stays open in the first tab; "Save" or "Cancel"
          closes that tab and the tree refreshes and selects the group.
        </p>
        <h3>Add your own group</h3>
        <ol>
          <li>
            Find the group it belongs under and click "+ Sub-group" on that row.
          </li>
          <li>
            Type the name, for example Export debtors under Sundry Debtors, and
            click "Save".
          </li>
        </ol>
        <p>
          The new group takes its nature and Schedule III head from the group
          above it.
        </p>
        <h3>Change, move or disable a group you added</h3>
        <p>
          Click "Edit" on its row. You can rename it or choose a different group
          in "Under". Groups are never deleted: tick "Disabled" in the
          "Switches" panel and "Save" to stop using one (untick it to bring it
          back). A group can be disabled only when the
          groups under it and the ledgers in it are disabled or moved first.
          Nothing new can be added under a disabled group.
        </p>
        <Note>
          Standard groups cannot be changed or disabled, because posting rules
          rely on them.
        </Note>
        <p>
          To add many groups at once, use "Actions" and "Import from Excel…"
          (see "Import, export and print"). Write the parent's name under "Under
          group", and list a new group after the group it sits under. Standard
          groups may stay in the file as they are. "Print" and "Download PDF"
          print the tree as it is shown, so fold or unfold it first.
        </p>
      </>
    ),
  },
  {
    id: "ledgers",
    title: "Ledgers",
    summary:
      "Accounts for parties, banks, expenses and income, with opening balances.",
    body: (
      <>
        <p>
          A ledger is one account: a customer, a supplier, a bank, an expense or
          an income head. Open Ledgers from "Masters" › "Ledgers" or the
          Dashboard.
        </p>
        <h3>The screen</h3>
        <ul>
          <li>
            <strong>The list on the left</strong> follows the group tree, with
            the number of ledgers and the net opening balance of each group.
            Fold groups with the arrows or "Show levels". Type in the search box
            to find a ledger by name or bank account number. Beside each group
            is "+ Ledger", and beside each ledger "Edit" (or "View" if you may
            only look) and "Duplicate"; each opens in a new browser tab. When
            you choose a group in "All groups", that group and the ones under
            it show even when empty, so you can add the first ledger to them.
          </li>
          <li>
            <strong>The panels on the right</strong> show the ledger you click:
            "Ledger Details" (group, nature, opening balance with the foreign
            currency amount and rate if it has one, currency, "Bill-Wise", bank
            details, whether it is in use and disabled, notes), for a customer
            or supplier "GST And Credit", "Addresses" and "Contacts", and
            "Opening Bills". After clicking a ledger, the ↑ and ↓ keys move
            through the list. The panels stay in view while the list scrolls.
          </li>
          <li>
            <strong>Activity</strong> at the bottom of the panels shows
            every change made to that ledger: who, when, and the old and new
            values (see "Change log").
          </li>
        </ul>
        <h3>Add a ledger</h3>
        <ol>
          <li>
            Click "Add ledger" at the top right, then choose the group in the
            form. Or click "+ Ledger" beside a group in the list, and the group
            is filled in. Either way the form opens in a new browser tab, and
            every group can be picked, including ones with no ledgers yet.
          </li>
          <li>Type the name and choose the group it goes under.</li>
          <li>
            If the company uses foreign currencies, choose the ledger's
            currency.
          </li>
          <li>
            For a bank ledger, fill in the bank, account number, IFSC and
            branch.
          </li>
          <li>
            Open "Opening Balance", enter the opening balance (see below) and
            click "Save"; the tab closes and the ledger is selected in the list.
          </li>
        </ol>
        <h3>Customers and suppliers</h3>
        <p>
          A ledger under Sundry Debtors is a customer, and one under Sundry
          Creditors is a supplier. A customer or supplier is shared by all
          companies in the group: its GST details, addresses, contacts and
          credit terms are kept once, and a change made in one company shows in
          every company. Each company has its own ledger for the party, with its
          own balance, bills, credit limit and salesman (for a customer) or
          purchaser (for a supplier), so each company can have different people
          looking after the same party.
        </p>
        <p>
          Click a ledger in the list and its details show on the right in
          panels: "Ledger Details", then "GST And Credit", "Addresses" and
          "Contacts" (for a customer or supplier), with the change log,
          "Activity", below.
        </p>
        <ul>
          <li>
            To add a party another company already deals with, click "+ Ledger"
            beside Sundry Debtors or Sundry Creditors, and pick it
            under "Existing Customer Or Supplier". Its details fill in; enter
            this company's credit limit and opening balance, and click "Save".
          </li>
          <li>
            A firm that both buys from and sells to this company can have two
            ledgers here: one under Sundry Debtors and one under Sundry
            Creditors. Add the second one with "+ Ledger" beside the other
            group, and pick the firm under "Existing Customer Or Supplier".
            MyERP names it, for example, "ABC Foods (Supplier)", because two
            ledgers cannot share a name. Both ledgers share the firm's GSTIN,
            addresses and contacts, and keep their own balances. A firm cannot
            have two ledgers on the same side in one company.
          </li>
          <li>
            To add a party to more companies in one go, tick them under
            "Companies that deal with this party" and click "Save". Each ticked
            company gets a ledger for the party under the same group.
          </li>
          <li>
            A new party's name must not be used by a customer or supplier of
            another company; pick the existing one instead.
          </li>
        </ul>
        <p>
          A customer or supplier form has folding sections, one open at a time:
          "Ledger", "Opening Balance", "GST And Credit", "Addresses",
          "Contacts", "Documents", "Products" and "Labels" (customers only).
          Click a section's title to open it; the closed ones show a short
          summary. "Save" and "Cancel" are in the green band at the top, "Disabled" and
          "Bill-Wise" under "Switches" at the right. In the "Ledger" section,
          "Under Group" is followed by the "Customer Number" (or "Vendor
          Number") and then the "GSTIN". The number is given automatically when you Save
          (CUST-00001, VEND-00001 and so on, running on across the group); a
          party that is a customer and a vendor (in one company or in different
          ones) has both. You may type your own number over it, but no two
          parties can share one. Search for a ledger by its number in the
          Ledgers list. Typing the GSTIN makes the party a registered one and
          fills in the state and PAN; the state decides the place of supply on
          invoices. "Fetch details" asks the GST portal for the name and address
          and fills them in (the name only when the box is empty or still holds
          the name typed in a 'Create "…"' picker). The registered address goes in the "Addresses" section,
          named after the party; you can rename it, for example "Head office".
          Its "PIN Code" and "City" are filled too: the city comes from the PIN
          list, or from the GST details when the PIN is not in the list yet (then
          use "Request Addition" before you save). It also warns if the GSTIN is not "Active" (cancelled or suspended).
          If the lookup is not available (the key is not set, the credits are
          used up, or the GST system is down) it says so, and you enter the
          details by hand.
        </p>
        <p>
          The "GST And Credit" section has two boxes, "GST" and "Credit". Together
          they hold:
        </p>
        <Fields
          rows={[
            [
              "GST type",
              "Registered (regular or composition), unregistered business, consumer, SEZ, or overseas. A registered party needs its GSTIN.",
            ],
            ["Country", "For an overseas party, in place of the state."],
            [
              "Credit limit",
              "This company's limit for the party. Leave blank for no limit.",
            ],
            [
              "Credit terms",
              'When payment is due, picked from the "Credit terms" list shared by the group, such as 30 days or 50% advance and 50% on delivery. The words under the box spell out the parts.',
            ],
            [
              "Price list",
              'For a customer, the "Selling" price list its sales use; for a supplier, the "Buying" list. Its own prices, in the "Item Prices" section, win over the list. See the chapter "Price lists".',
            ],
            [
              "Salesman or Purchaser",
              "The person in this company who looks after the customer (Salesman) or buys from the supplier (Purchaser). Other companies can choose someone else for the same party.",
            ],
            [
              "Preferred Transporter",
              'For a customer (when the company has the Sales module): the transporter this company usually sends the customer\'s goods with. For a supplier (when the company has the Purchase module): the transporter that usually brings the supplier\'s goods; leave it at "By Supplier" if the supplier sends them. Picked from the company\'s own "Transporters" (or "Create" a new one). Other companies can choose their own. A purchase order takes the supplier\'s one, and you can change it there.',
            ],
          ]}
        />
        <p>
          In the "Addresses" section, click "+ Add address" for each place the party
          has: office, godown, shop. Give each a name, and tick which one is the
          default billing address and which the default shipping address;
          documents pick these first. If the party is registered in another
          state too, enter that GSTIN on that address, then click "Fetch
          details" beside it: the address's name, state, address and PIN code
          are filled in from the GST portal, and you can change any of them.
        </p>
        <p>
          For an Indian address, click the "PIN code" box and type the PIN, or
          words of the city or state, and click the PIN you want in the list.
          The "City" and "State" boxes are then filled in for you; they are
          shown, not typed. A PIN that is not in the list is refused: click
          "PIN not in the list? Request Addition" (see the chapter "Countries
          and PIN codes"). An address saved before this rule keeps its city and
          state until you change its PIN. For an overseas party, the "Country"
          box is a type-to-search list of countries, and "Postal code" and
          "City" are typed freely. Company and branch forms still have their
          own "PIN code" and "City" boxes.
        </p>
        <p>
          In the "Contacts" section, click "+ Add contact" for each person you deal
          with: the owner, the purchase manager, accounts. Give each a name, and
          add their designation, phone and email. Under "Contact type", tick
          what each person is for: "Main" (the one to call first; only one per
          party), "Accounting", "Shipping", "Purchase" or "Sales". One person
          can have several types. When MyERP sends automated emails during
          transactions, it will send each to the contacts of the right type. The
          section titles show how many addresses and contacts the party has. If you
          click "Save" while a required field in a closed section is empty, MyERP
          opens that section and points to the field.
        </p>
        <p>
          In the "Documents" section, keep the papers of the customer or supplier:
          its GST certificate, PAN card, FSSAI licence, MSME / Udyam
          registration, agreements and a cancelled cheque. The section works once
          the party has been saved. Click "Add document", pick the "Document
          Type", give the "Number", and if the paper lapses, the "Renewal Date".
          Under "Attachments", click "Choose files" or drag files in (PDF,
          images, Word or Excel, up to 10 MB each, as many as you need); they
          are saved with the document. Click a file name in the list to open
          it. To take a wrong file off, open the document, click "Remove" beside
          it and then "Save". A document is never deleted: click "Disable" to hide it, and tick
          "Show disabled documents" to see it again. When a paper is renewed, add
          the new one; the old one stays on record. Documents that have lapsed or lapse
          within 90 days are listed under "Needs your attention" on the
          Dashboard.
        </p>
        <p>
          In the "Products" section, say which items may be sold to this customer
          or bought from this supplier. While the list is empty, any item can
          be. Once you add products (type in "Add Product" and pick the item),
          only those items are offered on quotations, orders and bills, plus
          any item with "Offer to all" ticked. Click "Remove" on a row to take
          an item off; remove every row to allow any item again. A disabled
          item, or one with "Allow sales" (customers) or "Allow purchase"
          (suppliers) unticked, stays off even when it is listed. Prices are
          not kept here. The section also shows "Their Item Name" and "Their Item
          Code" for each listed item, as set on the item under "Customer And
          Supplier Names"; they are read only here. Click "Actions" above the
          table, then "Print" or "Download PDF", for this party's item list
          with their names and codes.
        </p>
        <p>
          The "Labels" section, which only customers have, is empty for now. It will hold the label format for
          each item the customer buys (one format for this customer and item A,
          another for item B), used when labels are printed for a despatch.
        </p>
        <p>
          Clicking a party shows its details, addresses and contacts in the panels
          on the right.
        </p>
        <h3>Opening balances</h3>
        <p>
          The opening balance is the balance on the date the company's books
          begin. Enter the amount and choose Dr or Cr. For a ledger in a foreign
          currency, enter the amount in that currency and the rate; the rupee
          amount is worked out for you.
        </p>
        <p>
          For every ledger, the opening balance is in the "Opening Balance"
          section. Tick "Bill-Wise" under "Switches" at the right (customers and
          suppliers have it ticked from the start) and enter
          each unpaid bill with its reference, date, due date and amount. The
          opening balance is then the total of the bills. Bills must be dated
          before the books begin.
        </p>
        <Note>
          Ledgers are never deleted, so past entries always have their account.
          When a ledger (or a customer or supplier) is no longer needed, click
          "Edit", tick "Disabled" under "Switches" and "Save"; it then cannot be used in new
          entries. Untick it to bring it back.
        </Note>
        <Note>
          Once a ledger, customer or supplier is in use, a line at the top of
          its form says what uses it, and its key fields are greyed with a
          "Locked" tag: "Under Group", "Currency" and the "Bill-Wise" tick on
          a ledger, and "GST type", "GSTIN", "PAN" and "State" on a customer or
          supplier. Everything else stays open, including the name, credit
          terms and "Disabled".
        </Note>
        <p>
          To change many at once, use "Actions" at the top of the screen. See
          the chapter "Import, export and print".
        </p>
      </>
    ),
  },
  {
    id: "transporters",
    title: "Transporters",
    summary:
      "The couriers and road transporters you send goods with, such as a B2C and a B2B account with Delhivery.",
    body: (
      <>
        <p>
          A transporter is a courier, an aggregator such as Shiprocket, an
          airline or a road transporter that carries your goods. MyERP also
          keeps one list of couriers for everyone (Delhivery, Blue Dart, DP
          World and Shiprocket to start with), which gives the tracking page,
          the tracking number check and which PIN codes a courier serves. A
          transporter can point at one of those, or stand alone when it is not
          in the list, such as a local road transporter. One courier can have
          more than one transporter, for example "Delhivery B2C" for parcels and
          "Delhivery B2B" for heavier freight, because each has its own rates.
          This screen shows only for a company that uses the Sales module.
        </p>
        <p>
          On a transporter's line, "Preferred By" on the right shows how many
          customers and suppliers have it as their "Preferred Transporter" (see the
          chapter "Ledgers"). Such a transporter, or one on a submitted purchase
          order, counts as in use, so its courier and
          service stay locked, but you can still disable it: customers keep it
          and it is no longer offered to others.
        </p>
        <h3>Add a transporter</h3>
        <ol>
          <li>
            Pick the company at the top right, then click "Masters" in the top
            menu, then "Transporters".
          </li>
          <li>
            Click "Add transporter". The form opens in a new browser tab.
          </li>
          <li>
            Fill in the form (see below) and click "Save"; the tab closes and
            the new transporter is selected in the list.
          </li>
        </ol>
        <p>
          Click a row in the list to see that transporter's details on the
          right, with its activity below. To change one, click "Edit" on its
          row (or double-click the row); "Duplicate" starts a new one as a copy.
          Each opens in a new tab.
        </p>
        <Fields
          rows={[
            [
              "Name",
              'What the transporter is called on screens, for example "Blue Dart B2B". Each name is used once per company.',
            ],
            [
              "GSTIN",
              "Required. It is the Transporter ID on an e-way bill. The state is read from its first two digits. A courier with a B2C and a B2B account uses the same GSTIN on both.",
            ],
            [
              "Courier in MyERP's list",
              'Pick the courier from the list, or choose "Not in the list" for a transporter that is not there; you can then write a "Note for the MyERP team", and the team sees the transporter and can add it to the list for everyone.',
            ],
            [
              "Service",
              '"B2C (parcel / express)", "B2B (freight)" or "Aggregator" (Shiprocket).',
            ],
            [
              "Contact",
              "The contact person, phone and email. The transporter's pickup details come from the sales invoice, so there is no address here.",
            ],
            [
              "Account or customer code",
              "The code the transporter gave you, to find the account on their bills.",
            ],
            ["Notes", "Anything worth knowing."],
          ]}
        />
        <p>
          The pickup address and other details a booking needs come from the
          sales invoice, not from this form. When the courier you picked lists
          credentials, the form shows an "API Credentials" box with one entry
          for each, where you put your own login with that courier. A secret is
          stored locked and is never shown again: it appears as "Saved" with a
          "Change" button, and leaving it alone keeps it. Each company has its
          own credentials, "Duplicate" does not copy them, they are left out of
          the Excel file, and the activity log shows only the date they were
          saved, never the values. Once a shipment has been entered against a transporter, its "Courier
          in MyERP's list" and "Service" cannot be changed. The name, GSTIN and
          notes can still be corrected. A transporter in use shows a line "In
          use: ..." at the top of its form and those two fields are greyed with
          a "Locked" tag. Transporters are never deleted: on the form, tick
          "Disabled" under "Switches" to stop offering one, and untick it to
          bring it back.
        </p>
        <p>
          To add or change many transporters at once, use "Actions" at the top
          of the screen (see "Import, export and print"). In the file, "Courier
          in MyERP's list" is the courier's name as in MyERP's list, for example
          "Delhivery", and can stay empty; "GSTIN" must be filled.
        </p>
      </>
    ),
  },
  {
    id: "shipments",
    title: "Shipments",
    summary:
      "Every AWB sent out by courier, where it is now, and which ones need action.",
    body: (
      <>
        <p>
          Open it from "Sales" in the top menu, then "Shipments". It lists the
          shipments of the company picked at the top right. Until each courier's
          tracking is connected to MyERP, the despatch team types the status
          from the courier's website. Later MyERP will fetch it every morning by
          itself, and email the despatch team a summary.
        </p>
        <p>
          Before the first shipment, add the company's transporters (the
          "Transporters" button at the top, or "Masters", "Transporters").
        </p>
        <h3>The lists</h3>
        <Fields
          rows={[
            [
              "Needs action",
              'Open shipments with a problem: "Delivery failed", "Held", "Returning to us (RTO)", "Lost or damaged", past the expected delivery date, not picked up by the evening after booking, or no movement for 3 days.',
            ],
            ["Open", "Everything not yet delivered, returned or cancelled."],
            ["Delivered", "Shipments the courier has delivered."],
            ["All", "Everything, including cancelled ones (shown greyed)."],
          ]}
        />
        <p>
          "Search" finds a shipment by AWB, customer, invoice number, city or
          PIN code.
        </p>
        <h3>Add a shipment</h3>
        <ol>
          <li>Click "Add shipment".</li>
          <li>
            Pick the "Transporter" and type the "AWB (tracking number)". Spaces
            are dropped.
          </li>
          <li>
            Fill in who it went to: the "Customer" and the "Invoice or delivery
            note number" (for now, the ERPNext number), with the city and "PIN
            code".
          </li>
          <li>
            Give the "Packages", "Weight (kg)" and "Payment". For "Cash on
            delivery", give the "Amount to collect (₹)".
          </li>
          <li>Click "Save". The shipment starts as "Booked".</li>
        </ol>
        <Note>
          The same AWB cannot be entered twice for one courier. If an AWB was
          typed wrongly, open the shipment and click "Cancel shipment" with the
          reason; the number can then be entered again.
        </Note>
        <h3>Update the status</h3>
        <ol>
          <li>Click "Open" on the shipment.</li>
          <li>
            Under "Add status", pick the "Status", the time it happened
            ("When"), and the "Place". Copy what the courier's website says into
            "Remarks".
          </li>
          <li>For "Delivered", give who received it in "Received by".</li>
          <li>
            Click "Save". The shipment takes the status with the latest time.
          </li>
        </ol>
        <p>
          "Status history" shows every status with who entered it. Statuses are
          never changed or removed: if one was wrong, add the right one with a
          later time. "Edit details" corrects the customer, invoice number,
          weight and the like. Once the courier itself has reported on a
          shipment, its transporter and AWB are fixed.
        </p>
      </>
    ),
  },
  {
    id: "purchase-orders",
    title: "Purchase orders",
    summary:
      "What the company asks a supplier for: drafts, submit and number, cancel. Nothing is posted to the books.",
    body: (
      <>
        <p>
          A purchase order says what you asked a supplier for, at what rate and
          by when. It is the first step of purchase: the goods receipt (GRN), the
          purchase invoice and the purchase return come next and will be made
          from it. A purchase order posts nothing to the books or to stock.
        </p>
        <h3>Find the purchase orders</h3>
        <p>
          Click "Entry" in the top menu, point at "Purchase" and click
          "Purchase Order" in the list that opens to the right (on a phone,
          tap "Purchase" to open it). The orders are those of the company picked
          at the top right. "Entry" shows only when that company uses the
          Purchase module and your role may see purchase.
        </p>
        <p>
          The list runs across the whole screen. "Open (drafts and ordered)"
          shows first; pick "Drafts", "Received or closed", "Cancelled" or "All"
          in the box above the list. Every column has its own "Search" box under
          its heading: type in as many as you like, and only orders matching all
          of them stay. "Clear searches" empties them. Click an order to see its
          details and activity at the right, with "Open" and "Print"; click it again to
          close the panel. With a draft clicked, "Edit" beside "New purchase
          order" at the top opens it for changes. Double-click an order or
          press Enter to open it. "Duplicate" is on the order's own page. Print
          and PDF of the list are under "Actions".
        </p>
        <h3>Make a purchase order</h3>
        <ol>
          <li>
            Click "New purchase order" (it opens in a new browser tab).
          </li>
          <li>
            Under "Supplier and Dates" pick the "Supplier". If it is not there yet,
            type its name and click 'Create "…"': the "Add ledger" form opens in a
            new browser tab, under "Sundry Creditors" with the name filled in.
            Type its GSTIN and click "Fetch details": the name you typed is
            replaced by the name on the GST record. Fill in its credit terms and
            contacts and click "Save"; the tab closes and the order picks the
            new supplier with its credit term and contacts (only people who may
            add masters see this). The supplier's "Credit Term" and
            "Transporter" fill in by themselves; you can change them for this
            order. "Transporter" is "By Supplier" when the supplier sends the
            goods, or one of the company's transporters. Fill in the
            "Order Date", "Deliver To" (the branch the goods come to; the line
            under it says which store they go to), and if you like the
            "Expected Delivery" date and the "Supplier's Quote Ref".
          </li>
          <li>
            Under "Addresses", "Bill To" starts as the branch ticked as the
            default billing one (else the head office); pick another branch if
            the bill should name it. "Ship To" is the "Deliver To" branch. Pick
            the "Supplier Address" from the supplier's addresses (its default
            billing address to start with). Each shows as it will print: the
            street, "City - PIN", the state, then GSTIN, FSSAI, contact person,
            phone and email (from the branch, or from the company when the
            branch has none; FSSAI from "Licences and certificates" and from the
            supplier's documents). The supplier's address is kept on the order
            as it was, even if the supplier's addresses change later.
          </li>
          <li>
            For an overseas supplier an "Import Details" section appears. The
            order is in the "Currency" of the supplier's ledger (rates, totals
            and the print are in that currency, with no GST and no rupee value
            or exchange rate). Fill in the "Incoterms" and "Named Place", the
            "Mode of Shipment", "Port of Loading" and "Port of Discharge",
            "Country of Origin", "Latest Shipment Date", "Payment Method",
            "Partial Shipment", "Transhipment" and "Insurance By", tick the
            "Documents Required" and write the "Packing and Marking". The next
            order to the same supplier starts with these details (except the
            date).
          </li>
          <li>
            Under "Supplier Contacts and Agent", tick "Send Mail" for each
            person who should get the order by mail. The supplier's purchase
            contacts and its main contact are ticked to start with; a contact
            with no email cannot be ticked. If an agent buys for you, pick it as the
            "Buying Agent": either a broker or firm from the suppliers list
            (marked "Supplier"; add it as a supplier first) or one of your own
            employees (marked "Employee"), and tick who of them gets the mail. Contacts themselves are added on the supplier's ledger.
            Tick "WhatsApp" for each person who should also get the order on
            WhatsApp; a contact with no phone number cannot be ticked. For now
            the ticks are only kept on the order: sending on WhatsApp comes
            later.
          </li>
          <li>
            Under "Items" pick an item in the empty row. Only items that may be
            bought from this supplier are offered (see the supplier's Products
            list). The box under the item fills in with the item's "Purchase
            description"; change it for this order if you like (plain text,
            printed under the item name). The unit starts as the item's
            purchase unit. Type the "Qty".
            The "Rate" fills in from the supplier's own Item Prices, or else its
            "Buying" price list, and the line under it says which; type over it
            to use another rate. Add a "Disc %" if the supplier gives one. A new
            empty row appears for the next item; "✕" removes a line.
          </li>
          <li>
            Under "Charges", click "+ Add charge" for an extra the supplier
            bills on the order, such as freight, packing or insurance. Each
            charge is a service item ticked "Use as Purchase Charge" in the
            Items master. Pick its "Basis": "Fixed" (type the "Amount"), "% of
            items" (a percent of the items' taxable value) or "Per unit" (a
            rate on the total quantity, only when every line is in the same
            unit). The "GST %" starts as the item's rate and can be changed; an
            import has no GST column. "Add to Stock Cost" says how the charge is
            spread into the cost of the goods: "By Quantity", "By Value", or
            "No" for an expense that is not part of stock cost. "Stock Cost per
            Item" below shows an estimate; the goods receipt works out the
            final cost. The "Totals" show "Items", "Charges" and the "Taxable
            Value".
          </li>
          <li>
            Under "Terms and Notes", "Terms and Conditions" starts with the
            supplier's own set, else the company's default (see the chapter
            "Terms and conditions"); picking another set brings its text. The
            "Terms for the Supplier" box holds this order's own copy, printed
            on the order: change it here for this one order. Once you change
            the text by hand, picking another supplier keeps it. The "Internal
            Note" is only for your own people.
          </li>
          <li>
            Click "Save" to keep it as a draft: the form stays open, so you can
            carry on adding and click "Save" again. A draft can be saved before
            it has any items. Click "Close" to leave it for later; open it
            again from the list ("Edit") to finish it. Click "Submit" to give
            the order its number and send it; an order needs at least one item
            to be submitted. After "Submit" the page stays open on the submitted
            order, saying "Submitted as …" with the time; "Close" closes it.
          </li>
        </ol>
        <p>
          The screen runs across the whole width. The boxes at the bottom show the "Totals" (taxable value, GST and the
          round off to the rupee), when payment falls due under the credit term
          ("Payment Due"; the exact dates are set on the purchase invoice) and
          the "Activity". GST comes from each item's rate on the order date. A
          supplier in the same state as the "Deliver To" branch charges CGST and
          SGST; one in another state charges IGST. An unregistered or
          composition supplier charges no GST, so its orders have none.
        </p>
        <h3>Print and PDF</h3>
        <p>
          Every entry screen has a "Print ▾" button with its other buttons; its list holds the print layouts ("Purchase order" for now; more layouts join this list). On the order, or on the entry form once the order is saved, "Print ▾" then "Purchase order" opens the order as the supplier gets it, in a new tab, with the print
          window: your letterhead, the "Supplier", "Bill To" and "Ship To" addresses, the dates, credit term and
          transporter, the items with their descriptions, the charges, a "Tax Summary" by HSN / SAC code, the totals, the
          amount in words, the terms and conditions and the signature. An import shows its shipment and payment terms,
          "Documents Required" and "Packing and Marking", in the order's currency with no GST. A draft prints with
          "DRAFT" across each page; a submitted order carries the signature of the person who submitted it (if one is saved under Users) and says "Approved by" who submitted it and when. "Our Contact" shows the person who made the order, with their mobile number. The supplier's box shows the people the order is mailed to, else its main contact. When the company has "Printing" ticked, the first page carries the small Lord Ganesha image at the top centre. "Download PDF" opens the same page: pick "Save as PDF" as the printer to keep a PDF.
          Pages after the first start with a short heading (logo, company, order number and date, the supplier "continued"); when the items run over, a page ends "Carried to page n" with the total so far and the next begins "Brought from page n-1". Every page has the order number and "Page n of m" at the foot.
        </p>
        <h3>Submit, change and cancel</h3>
        <ul>
          <li>
            "Submit" gives the order its number from the "Purchase order"
            series (see "Numbering") and makes it final: it can no longer be
            changed. Its date must fall in an open month of a fiscal year.
          </li>
          <li>
            A submitted order has a "Create ▾" button for the documents that
            follow from it: "Goods Receipt (goods received)" opens a new goods
            receipt for this order with its items filled in (see "Goods
            receipts"). "Purchase Invoice" (the supplier's bill) is greyed out
            until that screen is built. As goods are received the order's status
            becomes "Part received", then "Received".
          </li>
          <li>
            A submitted order shows a "Received" box: each stock line's
            "Ordered", "Received" and "Pending" quantity and its status
            ("Received", "… short", "… over", "Not received" or "Closed"). When
            the rest of a line will not come, click "Close Line", say why (for
            example "Supplier will not send balance") and click "Close Line"
            again: its pending quantity becomes 0 and the next goods receipt
            no longer offers it. When every line is received or closed the
            order's status becomes "Closed". "Reopen Line" undoes it. Closing
            and reopening are written to the order's Activity. A line on a
            draft goods receipt cannot be closed until that receipt is
            submitted or the line taken off it. Closing needs the right to
            submit purchase orders.
          </li>
          <li>
            "Email Supplier" on a submitted order writes one mail to the
            supplier about every line that came short ("Short"), did not come
            ("Not received") or came in excess ("Excess"), all ticked; untick a
            line under "Lines" to leave it out. "To" starts with the contacts
            the order was mailed to and "CC" with you; type to add a supplier
            contact, a colleague or any address, and click "×" to take one
            off. The "Subject" follows the ticked lines ("Short and Excess
            Supply against PO No : …") and can be changed, as can the opening
            and closing words. The lines go in a grid. "Attach" adds the goods
            receipt as a PDF. "Send" sends it from the company's mail account
            (set under the company's "Mail Account"); replies come to you, and
            the order's Activity keeps a note of what was sent and to whom.
          </li>
          <li>
            To change a submitted order, open it, click "Cancel order", say why,
            and click "Cancel order" again; then click "Duplicate", change the
            copy and submit it. A cancelled order stays in the list with its
            reason.
          </li>
          <li>
            Once a submitted order names a supplier, item or unit, those count
            as "in use" and their key fields lock. A draft does not.
          </li>
        </ul>
        <h3>Attachments</h3>
        <p>
          Every entry screen has an "Attachments" box near the foot. Once the
          order is saved, drop files on it, or click "choose files" (or "take a
          photo" on a phone) to add the supplier's challan or invoice, the lorry
          receipt (LR), the e-way bill, photos and other papers: PDF, pictures,
          Word or Excel, up to 10 MB each. The list shows each "File", its
          "Type" (pick another from the list to change it), "Added By" and
          "Added On"; "Open" shows the file and "×" removes it. Files stay with
          the order after Submit, and more can still be added later. Adding
          or removing a file is written to the order's Activity. Anyone who may make orders may add files; others, such as "Storekeeper", only see and open them.
        </p>
        <Note>
          Who may do what follows the role: "Purchase" may make, change and
          submit orders; cancelling needs an Owner or a role with "cancel" for
          purchase. People who may only look see "Open", never "Edit".
        </Note>
      </>
    ),
  },
  {
    id: "goods-receipts",
    title: "Goods receipts",
    summary:
      "What arrived against purchase orders, put away into bins and batches. Submit puts it into stock and the books.",
    body: (
      <>
        <p>
          A goods receipt (GRN) records the goods that came into one of your
          warehouses against a supplier's purchase orders: how much arrived,
          how much was rejected, and which bins and batches the rest went into.
          Open it from "Entry" in the top menu, then "Purchase", then "Goods
          Receipt", or from a purchase order's "Create ▾" button. The Purchase
          team and the stores (Storekeeper) can both make receipts.
        </p>
        <h3>Make a receipt</h3>
        <ol>
          <li>
            Click "New goods receipt". The form opens in a new tab. Pick the
            "Supplier" (only suppliers with open orders are listed), the
            "Receipt Date" and the "Receiving Warehouse" (the branch the goods
            came into).
          </li>
          <li>
            The supplier's open orders for that warehouse are listed under
            "Purchase Orders". Tick the ones the goods came against and click
            "Get items": each item still pending comes in with its pending
            quantity.
          </li>
          <li>
            Fill in the supplier's challan or invoice number and date, the
            "Transporter", "LR / Docket No", "Vehicle No", "E-way Bill No" and
            who received the goods.
          </li>
          <li>
            On each item, change "Received" to what actually came and put any
            damaged or short quantity in "Rejected". "Accepted" is the
            difference; only that goes into stock.
          </li>
          <li>
            Under the item, "Put away into bins" says where the accepted
            quantity went. Pick a "Bin" (or an area such as "AC Store") and,
            for a batch-tracked item, its "Batch No". Click "+ Add bin" to
            split it, for example 300 Kg in one bin and 300 Kg in another. The
            line says "600 of 600 Kg put away" once it all has a place.
          </li>
          <li>
            If the goods came in bags, boxes or drums, say so on each bin row:
            "Packages" (how many), "Package Type" ("Bag") and "Qty per
            Package". The quantity is then worked out: 5 bags of 20 Kg in bin
            B1 make 100 Kg. Bags of another size, or in another bin, take a row
            of their own ("+ Add bin"), for example 1 bag of 10 Kg in bin B2;
            the line then says "110 of 110 Kg put away · 6 bags". The packing
            differs from one receipt to the next, so it is typed on each
            receipt. Leave "Packages" blank for loose goods.
          </li>
          <li>
            "Batch No" lists the item's batches. For a new batch, type its
            number and pick 'New batch "…"', then give its "Mfg Date" and
            "Expiry" (leave Expiry blank to have it worked out from the item's
            best-before). New batches are added to the Batches master on
            Submit. Batch numbers only need to be different within one item.
          </li>
          <li>
            "Save" keeps a draft to finish later. "Submit" gives the receipt
            its number from the "Goods receipt (GRN)" series and posts it.
          </li>
        </ol>
        <h3>What Submit does</h3>
        <ul>
          <li>
            Puts the accepted goods into stock: one entry for each bin and
            batch, at the order's rate after discount, plus the order's charges
            marked "Add to Stock Cost" (spread by quantity or value).
          </li>
          <li>
            Books the value: "Stock" (the item group's Stock Ledger) Dr, "Goods
            Received but Bills not Received" Cr. No GST is booked; that comes
            with the supplier's bill. If an item group has no Stock Ledger for
            the company, Submit says which one to set in Masters › Item groups.
          </li>
          <li>
            Adds the accepted quantities to the orders, which become "Part
            received" or "Received".
          </li>
          <li>
            More than ordered may be accepted; the line turns amber with a
            warning. On Submit the Purchase team and the Owner get a
            notification (the bell at the top right) for each line that came
            over ("Over-receipt") or is still short ("Short receipt"), naming
            the order, item, quantities and who received it, and one ("Not
            received") listing the order's lines that did not come with it.
            Clicking a notification opens the purchase order with those lines
            marked, where a line can be closed; the order's Activity notes each
            one too.
          </li>
          <li>
            Gives every bag or box its own number, PK-000241 and on, shown in
            the receipt's "Packages" box with its item, batch, bin, the
            quantity received and left, and its status ("In stock"). The number
            is what the bag's sticker carries as a barcode, and the bags taken
            will be picked by it when stock is issued (to come). A
            cancelled receipt keeps its bags, marked "Cancelled".
          </li>
          <li>
            New batches of items marked "QC required" start as "Quarantine";
            release them on the Batches screen once checked. The "Quality
            Check" box records the carton (CFC) condition, whether the batch
            code printed on the packs matches, and who checked.
          </li>
        </ul>
        <p>
          A submitted receipt shows "Submitted as … on … at …", its "Postings"
          (the book entries) and its "Activity".
          A submitted receipt cannot be changed: click "Cancel receipt" and say
          why. Cancelling reverses the stock and the book entries and shows the
          goods as pending on the orders again. It is refused if any of the
          goods have since been issued or moved.
        </p>
        <h3>Printing the receipt, bin sheets and bag labels</h3>
        <p>
          "Print ▾" on a receipt lists its print layouts; each opens in a new
          tab and asks the printer straight away.
        </p>
        <ul>
          <li>
            "Goods Receipt Note": one A4 page with the supplier, order,
            challan and transporter, the "Items Received" (ordered, received,
            rejected, accepted, packages), the "Bin-wise Storage" (each bin
            with its item, batch, bags and bag numbers, such as "PK-000001 to
            PK-000005"), the quality check, and four places to sign. No rates
            or values are printed.
          </li>
          <li>
            "Bin Sheets (A4)": one A4 page for each bin the receipt put goods
            into, to stick on or hang at the bin. The bin's name is printed
            large with its barcode and a QR code, then what this receipt put
            there and a list of its bags with a blank "Taken out (write in)"
            column.
          </li>
          <li>
            "Bag Labels (label printer, 100 × 50 mm)": one sticker per bag or
            box with the company, the bag number as text and as a barcode, the
            quantity, "Bag n of m", item, batch, expiry, bin, date and receipt
            number.
          </li>
          <li>
            "Bag Labels (A4 sheet, 24 per page)": the same stickers, smaller,
            on A4 label sheets of 3 × 8.
          </li>
        </ul>
        <p>
          The bin sheets and bag labels come once the receipt is submitted,
          because the bags get their numbers then. To reprint only some
          stickers (a torn one, say), tick those bags in the "Packages" box and
          then choose a bag label layout: only the ticked bags print.
          "Download PDF" saves the receipt as a file.
        </p>
        <p>
          Scanning a bin sheet's QR code with a phone opens the "Bin contents"
          page (after signing in): the bin's name and branch, "In This Bin
          Now" (each item and batch with its quantity at that moment, after
          all later receipts and issues) and "Bags And Boxes Here" (the bags
          still in it). Scanning the barcode with a scanner gives the bin's
          code, such as "LOC-000003".
        </p>
        <h3>Attachments</h3>
        <p>
          Every entry screen has an "Attachments" box near the foot. Once the
          receipt is saved, drop files on it, or click "choose files" (or "take a
          photo" on a phone) to add the supplier's challan or invoice, the lorry
          receipt (LR), the e-way bill, photos and other papers: PDF, pictures,
          Word or Excel, up to 10 MB each. The list shows each "File", its
          "Type" (pick another from the list to change it), "Added By" and
          "Added On"; "Open" shows the file and "×" removes it. Files stay with
          the receipt after Submit, and more can still be added later. Adding
          or removing a file is written to the receipt's Activity. Anyone who may make receipts may add files; others only see and open them.
        </p>
        <Note>
          Receipts are made and submitted by the Purchase or Storekeeper roles;
          cancelling needs an Owner or a role with "cancel" for purchase or
          stock. The date must fall in an open month of a fiscal year.
        </Note>
      </>
    ),
  },
  {
    id: "users",
    title: "Users",
    summary: "Letting people sign in and choosing what they can do.",
    body: (
      <>
        <p>
          Only people added here can sign in. They sign in with the Google
          account for the email you give. You need the permission to manage
          users to see this screen.
        </p>
        <h3>Add a user</h3>
        <ol>
          <li>Click "Admin" in the top menu, then "Users", then "Add user".</li>
          <li>
            Enter their email (their Google account), full name and "Mobile".
            The mobile number prints under "Our Contact" on the purchase
            orders they make.
          </li>
          <li>Tick their roles. Only an Owner can make someone an Owner.</li>
          <li>
            Tick the companies they may work in. None ticked means all
            companies.
          </li>
          <li>Click "Save".</li>
        </ol>
        <h3>Signature</h3>
        <p>
          Open the user and use "Upload image…" in the "Signature" box: a PNG
          or JPG of their signature on a white or clear background, up to 300
          KB. It is saved at once, and prints above "Authorised Signatory" on
          every purchase order they submit (a draft is never signed). "Change
          image…" replaces it and "Remove" takes it off. Only the person
          themselves or an Owner can change a signature.
        </p>
        <h3>Stop someone signing in</h3>
        <p>
          Click "Edit" on the user, then "Disable". They can no longer sign in;
          "Enable" lets them back. Their past work stays on record.
        </p>
        <p>
          The Activity column on the right shows who added or changed each user,
          including changes to their roles and companies.
        </p>
      </>
    ),
  },
  {
    id: "roles",
    title: "Roles",
    summary: "Sets of permissions, such as Accountant, Sales or Storekeeper.",
    body: (
      <>
        <p>
          A role is a set of permissions. MyERP comes with standard roles:
          Owner, Accountant, Sales, Purchase, Storekeeper, Production
          supervisor, Quality and Viewer. A person can have more than one role
          and gets everything each allows.
        </p>
        <p>
          Owner can do everything and cannot be changed. Only an Owner can
          change roles.
        </p>
        <h3>Make or change a role</h3>
        <ol>
          <li>
            Click "Admin" in the top menu, then "User roles", then "New role",
            or "Edit" on a role.
          </li>
          <li>
            Give it a name and description, tick the permissions in each area,
            and click "Save".
          </li>
        </ol>
        <p>
          Under Masters, "View, export and print" lets a person see masters and
          download or print their lists, and "Import from a file" lets them
          bring in masters from Excel (they also need "Create and edit"). No
          standard role except Owner has "Import from a file" until you tick it.
        </p>
        <p>
          Roles are never deleted. Standard roles can be edited but not
          disabled. A role you made can be disabled with "Disable" once no
          active user has it; a disabled role cannot be given to anyone
          ("Enable" brings it back).
        </p>
        <p>
          The Activity column on the right shows every change to roles and their
          permissions.
        </p>
      </>
    ),
  },
  {
    id: "change-log",
    title: "Change log",
    summary: "Who changed which master, when, and what it was before.",
    body: (
      <>
        <p>
          MyERP records every change to its masters by itself: companies,
          branches, licences and certificates, ledger groups, ledgers, users and
          roles. Each change shows who made it, when, and the old and new value
          of every field that changed. Nobody can edit or delete the log, not
          even an Owner.
        </p>
        <h3>Where to see it</h3>
        <p>
          The log shows as "Activity" beside the screen it belongs to: in a
          column on the right, or below the screen when the window is narrow,
          such as on a phone. The latest change is at the top.
        </p>
        <ul>
          <li>
            <strong>A company:</strong> the company page shows every change to
            that company's masters. Use the picker next to "Activity" to see
            only one kind of record, such as Ledgers.
          </li>
          <li>
            <strong>Ledger groups:</strong> the Ledger groups screen shows
            changes to groups.
          </li>
          <li>
            <strong>One ledger:</strong> click the ledger; its activity is at
            the bottom of the side panel.
          </li>
          <li>
            <strong>Users and roles:</strong> on the Users and Roles screens.
            You need the permission to manage users.
          </li>
        </ul>
        <h3>Reading an entry</h3>
        <ul>
          <li>
            <strong>Added</strong> lists what was filled in when the record was
            made.
          </li>
          <li>
            <strong>Changed</strong> shows each field as old → new. The old
            value is struck through; "blank" means the field was empty.
          </li>
        </ul>
        <p>
          One "Save" makes one entry, even when it changes several things, such
          as a ledger's balance and its opening bills. A save that fails, or
          changes nothing, adds nothing. The 50 latest changes show first; click
          "Show older changes" for more.
        </p>
        <Note>
          What MyERP sets up for a new company by itself (the Head office
          branch, the standard ledger groups and the Cash ledger) is not listed;
          the company's own entry is.
        </Note>
      </>
    ),
  },
];
