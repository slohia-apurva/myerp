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

        <h3>Lists stay up to date</h3>
        <p>
          You can also add a missing record the long way: open its master
          (for example "Masters", "Ledgers", "Add ledger") in another tab or
          window, save it there, and come back. Every screen reads its lists
          again the moment you return to its tab or click into its window, so
          the new record is already in the list when you open it. What you
          had filled in on the form stays as it was. The same happens for
          records someone else added, or ones brought in with "Import from
          Excel…".
        </p>

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

        <h3>Searching a list</h3>
        <p>
          On the masters lists ("Items", "Units", "Brands", "Credit terms",
          "Price lists", "Terms", "Batches", "Transporters", "HSN codes",
          "Countries" and "PIN codes") there is a search box under each column
          heading. Type in one or more of them: the list keeps only the lines
          that match every box (and the search box above the list, if you used
          it too). Words can be in any order and capitals do not matter. Click
          the small cross in a box to empty it. If nothing is left, the list
          says "Nothing matches the column searches." "Print" and "Download PDF"
          under "Actions" print only the lines you can see.
        </p>
        <p>
          As you scroll down a long list, the search box, the column headings
          and the column search boxes stay at the top of the window, just under
          the green title band, so you always see which column is which. The
          tree lists ("Ledger groups", "Ledgers", "Item groups") keep their
          headings at the top too, but fold by level instead of having column
          search boxes.
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
            opens this manual at the page for the screen you are on. On a
            phone the menu runs onto two lines, with the company on its own
            line under it and then the bell, "Help" and "Sign out".
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
          menu (Owners only). A new company starts with a Head office branch,
          the standard ledger groups, a "Cash" ledger and the six fixed system
          ledgers (see "Ledgers").
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
              "Deduct TDS on purchase of goods (194Q)",
              "Tick it when the company's turnover last year was above ₹10 crore. Purchase bills then deduct TDS under 194Q (0.1%) on what a supplier bills for goods above ₹50,00,000 in the year.",
            ],
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
              "Attachments",
              'Shown when editing a saved company. Under "Attachment Needed to Submit", tick each entry type (Purchase Order, Goods Receipt, Purchase Invoice) that must have at least one file in its "Attachments" box before it can be submitted. "Save" still keeps a draft without a file; "Submit" without one saves the draft and asks for the file. New entry types join the list unticked as they are built.',
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
            ["Company", "Shown for reference; it cannot be changed here."],
            [
              "Branch Name",
              'Just the branch, without the company\'s name, for example Sankrail-2. Screens show it as typed; prints show "Company (Branch Name)", for example "Apurvam Organics LLP (Sankrail-2)".',
            ],
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
          To bring your items across from ERPNext, use "Admin", "Migration
          Tools" (see that chapter).
        </p>
        <p>
          People whose role may see stock also get an "In Stock" column: the
          quantity of each item in stock today in the company picked at the top
          right, in its stock unit. Click the figure to open the "Stock Summary"
          of that item in a new tab, with its batches and the bins they are in.
          Under "Item Details" a "Stock" box shows the quantity and value in each
          warehouse, the batches with their expiry dates, and when the item was
          last received (click the entry number to open it). Its "Bins and
          batches" button opens the same Stock Summary, and "Stock Ledger" lists
          every move of the item in and out. See the chapter "Stock reports".
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
            goods unless changed on the order. "Use as Sales Charge" in the
            same panel offers it under "Charges" on a sales order.
          </li>
          <li>
            On the "Sales" tab, write the "Sales description" customers should
            see on quotations, orders and bills (both descriptions are plain
            text; on a printed document they show a little smaller, under the
            item name in bold), and pick the "Default sales
            unit" (for example Carton). Fill in the "MRP (₹)", the "USP (₹)"
            (Unit Selling Price, an amount) with "USP Per" (the unit it is
            for, such as Kilogram (Kg)) and the "Batch No" printed on the
            pack. "Best before" is a number with
            "Days" or "Months": a manufacturing order adds it to the
            manufacturing date to work out the best-before date. On the
            "Purchase" tab write the "Purchase description" for suppliers (a
            purchase order line starts with it and can change it), pick
            the "Default purchase unit", pick the "Preferred supplier" (the
            supplier the stock check buys a shortage from, at its Supplier
            Prices; only suppliers are offered), and fill in the "Lead time in
            days" (the supplier's delivery time) and "Minimum order qty"
            (suggested purchases are rounded up to it; in the item's default
            unit). "TDS Section" is the section a purchase of
            the item deducts TDS under, for example "194C" for an Annual
            Maintenance (AMC); goods usually leave it empty (they go by 194Q when
            the company deducts it), and a service left empty takes the
            supplier's default. The default units are picked from the
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
            The "Stock Planning" section says, for each branch, how much stock
            the item must keep and how a shortage is filled. Choose the "Main
            fulfilment": "Purchase" if the item is bought, "Manufacture" if it
            is made in-house, or "Customer Provided" if the customer supplies
            it. A "Customer Provided" item also needs its "Customer": whose
            goods it is. Each customer's goods have an item of their own, so it
            is set once here and every BOM, Manufacturing Order, Stock Receipt
            and Stock Delivery takes it from the item. Like the item's other
            key fields, it cannot change once the item is in use. Items made
            before this box came were filled in from whose stock they are;
            any left over show "Customer not set" until it is chosen. An item to be manufactured shows a "BOMs" box on its page with
            its BOM versions, "Open" and "New BOM" (see "BOMs"). Under "By Branch", click "Add branch" for each branch that
            should be checked, pick the "Branch" (only branches that keep stock
            are offered) and its "Fulfilment", which starts as the main one:
            "Purchase", "Manufacture", "Transfer" or "Customer Provided". For
            "Transfer" pick "Transfer From" (another branch of the same company)
            and give the "Transfer Days" the goods take on the way; a transfer
            branch's shortage is added to what that branch needs. Fill in the
            "Safety Stock" (the least the branch should hold) and "Order Up To"
            (the level a refill brings it back to; left empty, a refill goes up
            to the safety stock, and it cannot be below it). Quantities are in
            the item's default unit. A branch not listed is not checked for the
            item, and "Main fulfilment" must be set once there is a branch line.
            An item that keeps no stock has no stock planning. Click "Remove" to
            take a branch off.
          </li>
          <li>
            On the "Stock and quality" tab, in the "Switches" box tick "Track batches"
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
        <h3>Expense Account</h3>
        <p>
          The "Accounts" section of the item form has one row for each company,
          with its "Expense Account": the ledger a purchase bill without goods
          receipt books this item to (for example "Repairs and Maintenance" for
          a printer's annual maintenance). Only expense ledgers are offered. Left
          empty, the item group's "COGS/Expense Ledger" is used. Save the item
          first; the section then opens. Items kept in stock go to stock as
          before.
        </p>
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
    id: "boms",
    title: "BOMs (bills of materials)",
    summary: "What one batch of an item needs: versions, the one default, where each material comes from, job work and the cost estimate.",
    body: (
      <>
        <p>
          A BOM says what one batch of an item needs: its materials, with a
          loss allowed on each, and the by-products and scrap it gives. Open
          "Masters", then "BOMs" (shown when the company has the Production
          module ticked). BOMs are kept for the whole group, like items. The
          list shows "BOM No", "Item", "Version", "Name", "Default", "Makes",
          "Materials" and "Status"; double-click a row to open its page. A BOM
          posts nothing in the books or the stock.
        </p>
        <h3>Versions and the default</h3>
        <p>
          An item can have several BOM versions, numbered 1, 2, 3 for that
          item (each also gets its own number, BOM-00001). Exactly one active
          version is the item's "Default", marked ★: planning and a new
          Manufacturing Order start from it, and the order can pick another
          active version instead. The first active version of an item becomes
          the default by itself. On a BOM's page, the "Versions" box at the
          right lists every version; "Make default" moves the ★. A "Draft" or
          disabled version is never offered to orders, and the default cannot
          be disabled until another version is made the default.
        </p>
        <h3>Make one</h3>
        <ol>
          <li>
            Click "New BOM" (or "New BOM" in the "BOMs" box of an item set to
            "Manufacture"). It opens in a new tab.
          </li>
          <li>
            Under "What It Makes" pick the "Item", give a "Version Name" (for
            example "New pouch, Nov 2026"; left empty it is "Version 2"), how
            much one batch makes ("Makes Qty" and "Makes Unit", one of the
            item's units), "Valid From", "Status", "Notes" and
            "Packing Notes" (how to pack it: pouch, cartons, sealing). The
            Packing Notes are copied onto each Manufacturing Order, where they
            can be changed, and print on its batch sheet.
          </li>
          <li>
            Under "Materials" add each material with its "Qty" (for the
            quantity the BOM makes), "Unit" and "Loss %". The loss is added on
            top when an order works out what to issue: 2.4 kg + 0.5% is
            2.412 kg. A material cannot be the item itself, cannot be listed
            twice, and cannot be made, through its own default BOM, from the
            item this BOM makes.
          </li>
          <li>
            Under "By-products and Scrap" add what a batch gives besides the
            item, with a "Value per Unit" (0 for scrap with no value). A value
            lowers the cost of the main item.
          </li>
          <li>Click "Save".</li>
        </ol>
        <p>
          "Duplicate as new version" on a BOM's page starts the next version
          of the same item with everything copied: change what is new and save.
          Once a Manufacturing Order uses a version, its materials can no
          longer change; make a new version instead.
        </p>
        <h3>Where materials come from</h3>
        <p>
          "Comes From" shows "Manufactured" for a material with a default BOM
          of its own (its page unfolds it to its own materials; "Show levels"
          1, 2 or All opens them level by level) or one whose "Main
          Fulfilment" is "Manufacture", "Customer's stock" for an item marked
          "Customer Provided", and "Purchased" for the rest.
        </p>
        <h3>Job work</h3>
        <p>
          A BOM is job work when any of its materials is an item marked
          "Customer Provided": it makes goods from a customer's own material,
          and may add some of ours (a carton, say). There is nothing to choose:
          the BOM shows "Job Work For" with the customer named on those items,
          and one BOM cannot use two customers' goods. The customer's
          items are taken from their stock and are only counted, never valued;
          our own materials are costed, and their cost goes to the product.
          Job work is billed under a SAC code and despatched under an HSN code,
          so the item should be a Service that keeps stock, with its SAC code
          and its "Delivery HSN" (Masters › Items); the BOM's page shows both
          as "Billed Under SAC" and "Despatched Under HSN", and warns when the
          item is not set up that way. A customer's goods are never posted to
          the books, only counted.
        </p>
        <h3>Cost (Estimate)</h3>
        <p>
          The page shows a "Rate ₹" and "Cost ₹" for each material and their
          total. A rate is today's FIFO value of the stock held, else the rate
          of the last receipt; a manufactured material is costed from its own
          default BOM. The "Cost (Estimate)" box gives the cost per stock unit
          of the item, next to the other versions' cost. A material never
          received has "no rate" and is named under the box.
        </p>
        <Note>
          "Actions ▾" on the list has "Import from Excel…", "Export to Excel",
          "Print" and "Download PDF". The file has the BOMs on one sheet and the
          materials and by-products on sheets of their own, each row naming
          its "BOM" by number. A new BOM in a file needs a number of its own
          (BOM-00050, say) so its materials can name it.
        </Note>
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
          description. To search one column only, type in the box under
          "HSN code" (the first digits of the code) or under "Description"
          (words from it). Click a code in the list to see its details on the
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
          "Countries" or "PIN codes", and type in the search box, or in the
          box under a column heading ("PIN Code", "City", "State") to search
          that column only. Click a line
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
          The screen has its tabs. "Customers" lists every customer group
          (tenant) with its status and its "Migration Tools" tick: untick it
          once that customer's data is across from its old program, and
          "Admin", "Migration Tools" leaves its menu. "Shared lists" shows each central list with
          the number of rows in it (click "Open" to look inside) and the "Load
          lists from a file" box. "GST Units" holds the official GST unit codes
          (UQC, such as KGS or NOS) every customer's units link to: type a
          "Code" and "Name" and click "Save" to add one, "Edit" to correct a
          name, "Disable" when a code is withdrawn (units that already use it
          keep it). "GST Rates" holds the rates every customer's
          items choose from: type a rate under "GST Rate (%)" and click "Add
          rate", or click "Disable" to stop offering a rate for new entries
          (items that already use it keep it; rates are never deleted).
          "TDS Sections" holds the TDS sections purchase bills use, with their
          rates ("Company / Firm %", "Individual / HUF %", "No PAN %") and
          limits ("One Bill Over ₹", "Year Over ₹") from a date ("From"). When
          the law changes, click "Add section" and add a new row for the same
          section with the new "From" date; bills use the row in force on their
          date. "Edit" corrects a row and "Disable" stops it. From 1 April
          2026 the Income-tax Act 2025 numbers TDS under section 393: each row
          from that date has its "New Act Section" (for example "393(1) Sl.
          6(i)" for the old 194C) beside the "Old Section", and the "Payment
          Code" the challan and the TDS return ask for (where there are two,
          the second is for an individual or HUF). "Late Interest % a Month" is
          the interest for deducting TDS late, shown on a TDS Adjustment. The
          rows from 1 April 2025
          have only the old number and serve bills dated before 1 April 2026.
          The list covers purchase and expense bills: contractors (194C),
          commission (194H), rent (194I(a), 194I(b)), buying land or a building
          (194IA), technical and professional fees (194J(a), 194J(b)),
          director's fees (194J(ba)) and purchase of goods (194Q). The rates
          loaded at the start are the usual ones and are to be confirmed by a
          CA.
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
    id: "migration",
    title: "Migration Tools",
    summary: "Bringing masters across from ERPNext, using its own export files.",
    body: (
      <>
        <p>
          "Admin", "Migration Tools" holds the imports from the program you are
          leaving. Each one reads that program's own export file as it is, checks
          every row the way the MyERP form would, and saves nothing until every
          row is right. Only the Owner, and roles with "Import from a file",
          see it. Once your data is across, MyERP support switches Migration
          Tools off for your group and it leaves the menu; it can be switched on
          again at any time.
        </p>
        <h3>Items from ERPNext</h3>
        <ol>
          <li>
            First add the item groups and brands in MyERP. The import only
            matches groups, brands and units; it never makes them. Where a
            MyERP name differs from the ERPNext one, write both in a name map
            (see below).
          </li>
          <li>
            In ERPNext open the Item list, then "Menu" and "Export". Tick "Select
            All", tick the child tables "UOMs" and "Taxes", choose Excel and
            download the file. Do not change it.
          </li>
          <li>
            In MyERP open "Admin", "Migration Tools", and click "Import Items…"
            on the "Items" line. Choose the file under "ERPNext Item Export" and,
            if you have one, the name map under "Name Map". Leave "Leave Out
            Disabled Items" ticked to skip items disabled in ERPNext. Under
            "Delivery HSN For Job-Work Items" give the goods code for items with
            a service code (starting 99) that keep stock, for example 09024040.
            Click "Check file".
          </li>
          <li>
            Problems are listed with the row number of your ERPNext file, for
            example an item group that is not in MyERP or an HSN code that is
            not in the HSN list. Fix them (in MyERP, in the name map or in the
            file) and check again. When every row is right, click "Import".
          </li>
        </ol>
        <p>
          A big file is checked and imported 500 items at a time; the screen
          shows which part it is on. Each part is saved as it goes, so if one
          part stops, the parts before it stay saved. Running the same file
          again is safe: items already imported are found by their code and
          show as "with no change".
        </p>
        <p>
          The name map is an Excel file with two sheets. "Item groups" has the
          ERPNext group in the first column and the MyERP group in a column
          headed "MyERP …"; "Units" does the same for units of measure (for
          example Pcs → Nos, Meter → Metre, Case → Carton). Names not in the
          map are matched as they are, by name or short name. Write "Leave
          out" (or "Not to be imported") as the MyERP group to keep a group's
          items out of the import, as for "Fixed Asset".
        </p>
        <p>
          Each item keeps its ERPNext item code (for example IT-012465) as its
          "Item number". An item already in MyERP with the same code, or the
          same name, gets the code and the file's details instead of a second
          copy. New items made in MyERP afterwards carry on the same series:
          after IT-012465 comes IT-012466.
        </p>
        <p>
          What comes across: item code, item name, item group, brand, default
          unit of measure (matched by name or short name, such as "Kg"), HSN/SAC
          (a code starting with 99 makes the item a "Service", any other a
          "Goods" item), "Maintain Stock", "Allow Purchase", "Allow Sales", "Has
          Batch No" (as "Track Batches") and "Disabled". The "UOMs" table becomes
          the item's units of measure, each holding its conversion factor of the
          default unit. The "Taxes" table becomes the GST rates: the rate is read
          from the template's name ("GST 5% - AO" is 5%), from its "Valid From"
          date, or from 01-07-2017 when it has none. An item with no tax
          template comes in without a GST rate; the check lists them so you can
          add the rate before billing. Description, safety stock, lead time,
          minimum order and every other ERPNext column are left out.
        </p>
        <p>
          More tools (customers and suppliers, ledgers with opening balances,
          opening stock) join the list as they are built.
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
    id: "sales-people",
    title: "People (salesmen, purchasers, stores)",
    summary:
      "The people who sell to customers, buy from suppliers or receive goods in the stores, picked on customers, suppliers and goods receipts.",
    body: (
      <>
        <p>
          People is one list shared by every company in the group. A person
          here does not need to sign in to MyERP. A customer picks its
          "Salesman" and a supplier its "Purchaser" from this list, and each
          company can pick someone different for the same party. A goods
          receipt picks "Received By" and "Checked By" from the people ticked
          "Stores".
        </p>
        <h3>Add a person</h3>
        <ol>
          <li>Click "Masters" in the top menu, then "People".</li>
          <li>
            Click "Add person". The form opens in a new browser tab. Give the
            "Name", and if you like the "Mobile", "Email" and "Notes".
          </li>
          <li>
            Under "Works As", tick "Salesman", "Purchaser", "Stores", or more
            than one. A Salesman is offered on customers, a Purchaser on
            suppliers, Stores on goods receipts.
          </li>
          <li>
            If the person also signs in to MyERP, pick them in "MyERP User".
            Otherwise leave it at "None (no sign-in)".
          </li>
          <li>Click "Save"; the tab closes and the person is selected in the list.</li>
        </ol>
        <p>
          You can also add someone straight from a customer, supplier or goods
          receipt: type the name in "Salesman", "Purchaser" or "Received By"
          and pick 'Create "…"'.
        </p>
        <p>
          Click a person in the list to see their details on the right, with
          their activity below. The "Parties" column counts the customers and
          suppliers that have picked them. Names must be different, whatever
          the capital letters. Someone picked as a customer's salesman keeps the
          "Salesman" tick, a supplier's purchaser keeps the "Purchaser" tick,
          and someone named on a goods receipt keeps the "Stores" tick. People are never deleted: tick "Disabled" to stop offering
          them; parties that already have them keep them. To change many at
          once, use "Actions" at the top of the screen (see "Import, export
          and print").
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
          company, with three ledgers to pick (click the box and type a few
          letters). "Stock Ledger" holds the value of the stock on hand and
          lists the ledgers under Stock-in-Hand. "COGS/Expense Ledger" takes
          the cost of stock goods when they are sold, of stock used inside the
          company or written off, and of items that keep no stock, such as
          stationery or a service; it lists expense ledgers. "Sales Ledger"
          takes the group's sales on sales invoices (and of a service group,
          charges such as freight); it lists income ledgers, such as one under
          Sales Accounts. Leave a company empty
          if it does not use the group. A group under a main group shows the
          same accounts read only, with a link to open the main group. The
          "Accounts" panel on the right of the list shows them too. An entry
          (such as a Goods Receipt) cannot be submitted while its items' main
          group lacks these ledgers; its "Set ledgers" button opens the group
          here, at the "Accounts" box.
        </p>
        <p>
          Once any stock entry or purchase is posted against a company's
          accounts, that company's row is greyed with the tag "Locked" and the
          reason; the other companies' rows stay open. A "Sales Ledger" still
          empty can be picked on a locked row; once picked, it locks too.
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
          pick their units from it. The list starts with the usual ones (Nos,
          Packet, Inner box, Carton, Pallet, Bag, Bottle, Kilogram, Gram, Tonne,
          Litre, Millilitre, Metre) and one unit for every other GST unit code,
          from Bale and Box to Square Foot, Unit and Yard, so every unit GST
          returns know is there already.
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
    summary: "A warehouse's areas, racks and bins.",
    body: (
      <>
        <p>
          A warehouse is a branch of the company: every branch holds goods
          unless it is ticked "No stock". It has areas, which are named zones
          such as Finished Goods, Receiving, Production and Despatch. Racks
          stand in an area (or straight in the warehouse), a rack holds bins,
          and a bin is a physical location where stock is kept. For example,
          the Finished Goods area of Sankrail-2 can hold five racks, each with
          its bins.
        </p>
        <h3>The default store</h3>
        <p>
          Goods need a place even in a simple office with no racks or bins, so
          every branch that holds stock has an area called "Store", marked
          "Default". You can rename it, but not disable it. Goods
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
        <h3>Put racks in an area</h3>
        <p>
          On the rack's form, pick the area in "In Area" and click "Save"; leave
          it empty for a rack straight in the warehouse. The list then shows the
          area with its racks under it (fold it with the arrow), and "Add rack"
          on the area's row adds a rack already in that area. You can give a
          rack an area, or move it to another, at any time: its bins and their
          stock go with it. Rack names still do not repeat within the
          warehouse. An area can be disabled only after its racks are disabled
          or moved out.
        </p>
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
          file a bin names its rack in "On rack / in area" and a rack names its
          area there (or leaves it blank); an area must come before its racks,
          and a rack before the bins on it.
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
            For an expense ledger, "TDS Section" is the section a purchase bill
            line booked to it deducts under (for example "194I(b)" for "Office
            Rent"). Left at "None", the supplier's default section is used.
          </li>
          <li>
            Open "Opening Balance", enter the opening balance (see below) and
            click "Save"; the tab closes and the ledger is selected in the list.
          </li>
        </ol>
        <h3>Fixed system ledgers</h3>
        <p>
          Every company has six ledgers that MyERP makes and posts to itself, for
          goods and bills that have not yet met, and for stock that is being
          made or is with a job worker:
        </p>
        <ul>
          <li>"Goods Received but Bills not Received", under Other Current Liabilities.</li>
          <li>"Bills Received but Goods not Received", under Other Current Assets.</li>
          <li>"Goods Delivered but Bills not Made", under Other Current Assets.</li>
          <li>"Bills Made but Goods not Delivered", under Other Current Liabilities.</li>
          <li>"Work in Progress", under Stock-in-Hand (Inventories).</li>
          <li>"Stock with Job Workers", under Stock-in-Hand (Inventories).</li>
        </ul>
        <p>
          Their panel shows "Type" as "Fixed System Ledger". Their name cannot be
          changed and they cannot be disabled, but the "Under Group" can be
          changed at any time, even after entries are posted to them, so your
          accountant can place them where they belong; past entries move with
          the ledger. Other ledgers MyERP posts to, such as "Round Off" or "Input
          CGST", show "System Ledger": they cannot be disabled, but can be renamed.
        </p>
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
              'The person in this company who looks after the customer (Salesman) or buys from the supplier (Purchaser), from the list in "Masters" › "People". A customer offers the people ticked "Salesman", a supplier those ticked "Purchaser"; type a new name and pick \'Create "…"\' to add someone. Other companies can choose someone else for the same party.',
            ],
            [
              "Deductee Type and Default TDS Section",
              'For a supplier. "Deductee Type" (Company, Firm or LLP, Individual or HUF, Others) sets the TDS rate; left at "From the PAN" it is read from the PAN\'s 4th letter. "Default TDS Section" is used on a purchase bill line whose item or ledger names no section, for example "194C" for a contractor. They are kept once for the supplier and used by every company. See "TDS" in the chapter "Purchase invoices".',
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
          Saved addresses and contacts each show as one line: an address with
          its "Name", "Address", "State" and which default it is; a contact
          with its "Name", "Designation", "Phone", "Email" and "Type". Click
          "Edit" at the end of a line to open it, change what you need, and
          click "Done" to fold it back into a line ("Remove" takes it off).
          A new address or contact opens ready to fill in. Nothing is kept
          until you click "Save" at the top of the page.
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
          add their designation, phone and email. Under "Contact Type", tick
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
    id: "insurance-policies",
    title: "Insurance policies",
    summary:
      "The company's marine, fire and stock policies, the cover left on each, and the top-ups that refill it.",
    body: (
      <>
        <p>
          Keep here every insurance policy the company holds: marine policies
          for goods moving inland or exported, and fire and stock policies. A
          marine policy is an open policy. Each order whose goods travel under
          it uses up part of its sum insured, and the insurer tops it up with an
          endorsement when it runs low. Policies belong to one company; pick
          the company at the top right, then click "Masters" in the top menu,
          then "Insurance policies".
        </p>
        <p>
          The list shows each policy with its "Total Cover" and, for a marine
          policy, the "Balance" left; a balance shown in red is below the
          policy's alert. Click a row to see its summary and Activity on the
          right. "Add policy", "Open" and "Duplicate" open the form in a new
          browser tab.
        </p>
        <h3>The form</h3>
        <ul>
          <li>
            "Policy Number", "Insurer" (the insurance company, picked from the
            company's suppliers; type a new name and click 'Create "…"' to add
            it), "Type of Insurance", "Valid From" and "Valid To" are required.
            The same policy number cannot be entered twice in a company.
          </li>
          <li>
            For a marine policy: "Covers" (purchases, sales or both), "Limit
            per Transit" (an order above it is flagged), "Insured Value" (the
            invoice value, or the invoice value plus 10%) and "Default For"
            (new orders start with this policy; only one policy is the default
            for purchases, and one for sales).
          </li>
          <li>
            Under "Sum Insured and Top-ups", give the "Starting Sum Insured"
            and its "Premium". Each time the insurer tops up the cover, click
            "+ Add Top-up" and fill in the "Date", "Endorsement No.", "Cover
            Added" and "Premium". "Total Cover" is the starting sum plus every
            top-up.
          </li>
          <li>
            "Alert When Balance Falls Below": when a submitted order takes the
            balance below this amount, Owners and Accountants get a notice under
            the bell asking for a top-up. "When Cover Runs Out" is either "Warn,
            keep insuring" (orders go on, with a warning on the order) or "Stop
            until topped up" (an order the balance cannot cover cannot be
            submitted until the top-up is added).
          </li>
          <li>
            "Send Declaration To" and "Copy To" are the insurer's or broker's
            email addresses for the daily list of insured orders, which is
            being built next.
          </li>
          <li>
            Once the policy is saved, add its copy and the endorsements under
            "Attachments". The "Disabled" tick on the right stops the policy
            being offered on new orders.
          </li>
        </ul>
        <p>
          The balance is the "Total Cover" less the insured value of every
          submitted purchase order naming the policy (cancelled orders give
          their cover back). Once an order names a policy, its "Insurer" and
          "Type of Insurance" are locked; the number, dates, cover and top-ups
          stay open.
        </p>
        <p>
          "Actions ▾" holds "Import from Excel…", "Export to Excel", "Print"
          and "Download PDF" (see "Import, export and print"); the top-ups go
          on a sheet of their own.
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
    id: "stock-check",
    title: "Stock check",
    summary: "Which items of a branch will fall below their safety stock, and draft purchase orders to refill them.",
    body: (
      <>
        <p>
          Open "Entry", then "Planning", then "Stock Check". It looks at one
          branch and lists the items whose "Stock Planning" line there (see the
          chapter "Items") says "Purchase" and that will fall below their
          "Safety Stock". Nothing is posted and nothing is sent: it only makes
          draft purchase orders when you ask.
        </p>
        <ol>
          <li>
            Pick the "Branch". "Show" is "Below Safety Stock" (only the items
            that are short) or "All Planned Items". "Item Group" narrows the
            list. "Check Now" works the figures out again.
          </li>
          <li>
            For each item the columns are: "In Stock" (what the branch holds
            now; goods in its "In Transit" place do not count yet),
            "Reserved" (still to deliver on the branch's sales orders, drafts
            included, draft stock transfers out of it and draft own use),
            "Incoming" (still
            to receive on the branch's purchase orders, drafts included, and
            stock transfers coming to it, drafts and those on the road),
            "Expected" (In Stock − Reserved
            + Incoming, in red when below the safety stock), "Safety" and
            "Order Up To". These are in the item's default unit.
          </li>
          <li>
            "Suggested" is how much to buy so the branch is back at "Order Up
            To" (or at the safety stock when that is empty), in the item's
            purchase unit, rounded up to the "Minimum order qty" in whole steps
            of it. For example 2,580 Packets is 107.5 Cartons of 24; with a
            minimum of 24 Cartons it becomes 120 Cartons. You can change it.
          </li>
          <li>
            Items are grouped by supplier: the item's "Preferred supplier" to
            start with, with its lead time and the date the goods should come
            by. Pick another supplier on a line to change it; "Rate ₹" is that
            supplier's rate from its Supplier Prices or buying price list. An
            item with no supplier is listed at the end until you pick one.
          </li>
          <li>
            Tick the lines to order and click "Create Purchase Orders". One
            draft order is made per supplier, with the supplier's credit term,
            transporter and purchaser, and "Expected Delivery" today plus the
            longest lead time. Open each one from the note at the top, check it
            and click "Submit" as usual.
          </li>
        </ol>
        <Note>
          Draft orders count as "Incoming" at once, so a check run again never
          orders the same goods twice. A cancelled order counts for nothing.
          A draft or open manufacturing order counts its materials still to
          issue as "Reserved" and what it will make as "Incoming". Items the
          branch makes are not ordered from this screen yet; that comes next
          with manufacturing orders.
        </Note>
        <h3>To Transfer</h3>
        <p>
          Items whose Stock Planning line at the branch says "Transfer" from
          another branch are listed under "To Transfer", grouped by the branch
          they come from, with its "Transfer Days" and the date they would
          arrive by. The figures are the same as for "To Buy". "Suggested" is
          in the item's sales unit, rounded up to whole units; there is no
          minimum order. "Free at Source" is what the source branch has: its In
          Stock − Reserved, in red when it is less than the quantity.
        </p>
        <p>
          Tick the lines and click "Create Stock Transfers": one draft stock
          transfer is made per source branch, with Expected Arrival today plus
          the Transfer Days. The source's stores open it, check it and click
          "Dispatch" (see "Stock transfers"). A source short of stock is only a
          warning: the draft counts as "Reserved" there, so that branch's own
          check buys or makes more. A source with another GSTIN cannot send by
          transfer (that is a sale), so its lines cannot be ticked. The drafts
          made and not yet dispatched are listed below the lines.
        </p>
        <h3>Daily run</h3>
        <p>
          The "Daily Run" box at the right sets the check to run by itself every
          morning. Tick "Run every morning and make draft purchase orders and
          stock transfers" and
          pick the hour in "Run At" (07:00 to start with). Only someone who may
          change masters can change it. At that hour, for every branch of the
          company with Stock Planning lines, it does what "Create Purchase
          Orders" does for every short item that has a supplier: one draft per
          supplier, with the note "Made by the daily Stock Check", and what
          "Create Stock Transfers" does for every short item to transfer. The
          Purchase people and the stores get a bell notice naming the drafts and
          any item with no Preferred Supplier; clicking it opens this screen for
          that branch.
        </p>
        <p>
          The drafts are never sent by themselves: open each one from "Draft
          Purchase Orders Made by Stock Check", check it and Submit it. A draft
          nobody has submitted still counts as "Incoming", so the next morning
          does not order it again. "Recent Runs" lists the last runs of the
          branch, daily or by hand, and what each made.
        </p>
      </>
    ),
  },
  {
    id: "stock-transfers",
    title: "Stock transfers",
    summary: "Goods sent from one branch to another of the same company and GSTIN: Draft, Dispatch, In Transit, Receive.",
    body: (
      <>
        <p>
          A stock transfer moves goods between two branches of the company
          that have the same GSTIN. It moves only our own goods, not a
          customer's ("Customer Provided" items). Open "Entry", then "Stock", then "Stock
          Transfer". The list shows every transfer with "From", "To", "Value ₹"
          and "Status"; "Show" picks Draft, In Transit, Received or Cancelled.
          "Entry" shows "Stock" when the company uses the Stock module and your
          role may see stock.
        </p>
        <h3>Make one</h3>
        <ol>
          <li>Click "New Transfer". It opens in a new tab.</li>
          <li>
            Pick the "From Branch" and, if the goods should come only from one
            area, the "From Area" ("Whole branch" otherwise). Pick the "To
            Branch" and the "To Area" the goods go to on receipt ("Default
            store" otherwise). A branch with another GSTIN is refused: that move
            is a sale in GST law (a tax invoice and a matching purchase), not a
            transfer.
          </li>
          <li>
            Give the "Transfer Date", and if you know them "Expected Arrival",
            "Transporter" ("Own vehicle" if none), "Vehicle No", "E-way Bill
            No" and a "Reason".
          </li>
          <li>
            Add the items with "Qty" and "Unit". "Free at From" shows what the
            From branch or area has free, in red when it is less than the
            quantity.
          </li>
          <li>
            Click "Save". The bins and batches are picked by the same rule as
            pick lists (earliest expiry first, held batches never) and show in
            "Taken From (bin · batch)". A draft already counts in the Stock
            Check: "Reserved" at From and "Incoming" at To.
          </li>
        </ol>
        <h3>Dispatch</h3>
        <p>
          Click "Dispatch" when the goods leave. The transfer gets its number
          (ST/...), the bins and batches are picked again with the stock as it
          is then, and the goods leave those bins at their FIFO cost. They now
          sit in the To branch's "In Transit" place at that same value. The
          books get nothing: both branches keep the company's one Stock
          Ledger, and the branch-wise stock value shows where the goods are.
          If there is not enough stock, a popup lists each short line with "Go
          to line"; the draft is kept. Packages taken whole move with the
          goods; an opened package stays at From. "Print" gives the Delivery
          Challan (items, HSN, quantity, value at cost, e-way bill number,
          "Not for sale: branch transfer").
        </p>
        <h3>Receive</h3>
        <ol>
          <li>
            When the goods arrive, open the transfer and click "Receive".
          </li>
          <li>
            For each bin and batch sent, give what came in "Received" and the
            place it goes in "Put Into" (the To Area or the default store to
            start with). Give "Received On".
          </li>
          <li>
            If less came than was sent, give the "Shortfall Reason". What did
            not arrive goes out of stock as a transit loss: Dr Stock
            Adjustment, Cr Stock, at its cost.
          </li>
          <li>Click "Receive". The lines show "Received" or "Short".</li>
        </ol>
        <p>
          The "Stock Posting" section shows each step, Dispatch and Receive,
          with what moves in the stock ledger and in the books: on a draft what
          will happen, afterwards what did.
        </p>
        <Note>
          "Cancel" drops a draft, or puts the goods of a transfer still in
          transit back into their bins at From. A received transfer cannot be
          cancelled: use "Create ▾", "Transfer back (send goods back)", which
          opens a new transfer the other way. Files such as the e-way bill go
          in "Attachments" at the right, also after Dispatch.
        </Note>
      </>
    ),
  },
  {
    id: "customer-stock",
    title: "Customer's goods: stock receipt and stock delivery",
    summary: "A customer's own goods coming in for job work and going back unused. Quantity only, held as that customer's stock.",
    body: (
      <>
        <p>
          Some goods in the warehouse are not ours: a customer sends their own
          tea to be packed, or their own pouches to pack it in. These are
          items marked "Customer Provided" on the item. They come in on a
          "Stock Receipt" and, if they go back unused, leave on a "Stock
          Delivery". Open "Entry", then "Stock", then "Stock Receipt" or "Stock
          Delivery". Each has its own list with "Show" (Draft, Submitted,
          Cancelled) and a search box over every column.
        </p>
        <p>
          Nothing is ever posted to the books for these goods: they are counted
          in quantity only. They are held as that customer's stock, apart from
          ours and from every other customer's. A delivery, or any other entry
          that takes them out, takes only what that customer has. A Stock
          Transfer does not take a customer's goods.
        </p>
        <h3>Stock Receipt</h3>
        <ol>
          <li>Click "New Stock Receipt". It opens in a new tab.</li>
          <li>
            Pick the "Branch" and, if you like, the "Area"
            where the goods go ("Receiving area or default store" otherwise).
            Give the "Date", the "Customer's Challan No" and "Challan Date",
            the "Transporter" ("By Customer" if they brought it), "Vehicle No",
            "E-way Bill No", who "Received By" and a "Reason", such as the job
            work order.
          </li>
          <li>
            Add the items with "Qty" and "Unit". Only items marked "Customer
            Provided" are listed. The "Customer" is not picked: it comes from
            the first item (each item names its customer in Masters › Items),
            and after that only that customer's items are offered. For each line pick where it is "Put In" (a
            bin or area; empty means the Area above), the "Batch" for an item
            that keeps batches (the customer's lot number will do), and how
            many "Bags" and of what "Bag Type".
          </li>
          <li>
            Click "Save" to keep a draft, or "Submit". Submit gives the number
            (SR/...), makes the batch if it is new, and puts the goods in as
            that customer's stock. Each bag gets its own number (PK-...), with
            the line's quantity shared equally between its bags.
          </li>
        </ol>
        <p>
          "Print ▾" gives the "Receipt Slip" (what came, where it was put,
          bags) and the "Bag Labels", on a label printer or an A4 sheet.
          "Create ▾", "Stock Delivery (send goods back)" opens a delivery for
          the same customer.
        </p>
        <h3>Stock Delivery</h3>
        <ol>
          <li>Click "New Stock Delivery".</li>
          <li>
            Pick the "Branch" and, if the goods should come from
            one area only, the "Area" ("Whole branch" otherwise). Give the
            "Date", "Transporter", "Vehicle No", "E-way Bill No", who "Handed
            Over By" and the "Reason".
          </li>
          <li>
            Add the items. The "Customer" comes from the first item, as on
            the receipt. "Customer's Stock" shows what that customer has at
            the branch, in red when it is less than the quantity.
          </li>
          <li>
            Click "Save". The bins and batches are picked from that customer's
            stock by the usual rule (earliest expiry first, whole bags by their
            numbers) and show in "Taken From (bin · batch)". Click "Submit"
            when the goods leave; they are picked again with the stock as it is
            then. If the customer has too little, a popup lists each short line
            with "Go to line" and the draft is kept.
          </li>
        </ol>
        <p>
          "Print ▾" gives the "Delivery Challan", marked "Returned to owner,
          not a sale", with the e-way bill number.
        </p>
        <Note>
          "Cancel" drops a draft. On a submitted receipt it takes the goods out
          of the customer's stock again, which is refused once any of them has
          been used or sent back (cancel that entry first); on a submitted
          delivery it puts the goods back in the bins they came from. Files
          such as the customer's challan go in "Attachments" at the right, also
          after Submit.
        </Note>
      </>
    ),
  },
  {
    id: "own-use",
    title: "Own use",
    summary: "Our own stock used inside the company (office, canteen, maintenance, R&D, damaged): out of stock at cost, charged to an expense ledger.",
    body: (
      <>
        <p>
          Own Use takes our own goods out of stock when they are used inside
          the company rather than sold: tea for the office pantry, material
          for maintenance or R&amp;D, goods damaged and thrown away. Open
          "Entry", then "Stock", then "Own Use". The list shows each entry with
          "Branch", "Items", "Reason", "Cost ₹" and "Status".
        </p>
        <h3>Make one</h3>
        <ol>
          <li>Click "New Own Use". It opens in a new tab.</li>
          <li>
            Pick the "Branch" and, if the goods should come from one area only,
            the "Area" ("Whole branch" otherwise). Give the "Date", who "Issued
            By" and the "Reason", such as "Office pantry, November".
          </li>
          <li>
            Add the items with "Qty" and "Unit". "Free Here" shows what is free
            at the place, in red when it is less than the quantity. Items
            marked "Customer Provided" are not listed: they are not ours to
            use.
          </li>
          <li>
            "Expense Ledger" shows where the cost goes: the item's own "Expense
            Account" for the company (Masters › Items), else its item group's
            COGS/Expense Ledger. Pick another expense ledger on the line to
            charge it elsewhere, for example "Staff Welfare".
          </li>
          <li>
            Click "Save". The bins and batches are picked by the usual rule
            (earliest expiry first) and show in "Taken From (bin · batch)". A
            draft already counts as "Reserved" in the Stock Check.
          </li>
        </ol>
        <h3>Submit</h3>
        <p>
          Click "Submit" when the goods are taken. The entry gets its number
          (OU/...), the bins are picked again with the stock as it is then, and
          the goods leave at their FIFO cost. The books get Dr each line's
          Expense Ledger, Cr the item group's Stock Ledger. The "Ledger
          Posting" section shows this: on a draft at today's cost, once
          submitted what was posted. If stock is short or a line has no
          expense ledger, a popup lists each line with "Go to line"; if the
          item group's Stock Ledger is not set, the missing-ledgers popup
          offers "Set ledgers" or "Ask to set". The draft is kept either way.
        </p>
        <p>
          "Print ▾" gives the "Issue Slip": items, where they were taken from,
          the expense ledger and the cost.
        </p>
        <Note>
          "Cancel" sets a draft aside, or puts the goods of a submitted entry
          back into the bins they came from and reverses the ledger entries.
          Files go in "Attachments" at the right, also after Submit.
        </Note>
      </>
    ),
  },
  {
    id: "manufacturing-orders",
    title: "Manufacturing orders",
    summary: "What to make, how much, by when and with which BOM version; its materials, Pack Details and batch sheet.",
    body: (
      <>
        <p>
          A Manufacturing Order says what to make, how much, by when and with
          which BOM version. Open "Entry", then "Production", then
          "Manufacturing Order" (the company needs the Production module). The
          list shows "MO No", "Item", "Qty", "BOM Version", "Batch No", "Due"
          and "Status"; "Show" picks open, draft, completed, closed, cancelled
          or all orders. The order posts nothing in the books or the stock:
          the materials leave with a Material Issue and the goods come in with
          a Production Entry (both coming later, under "Create ▾").
        </p>
        <h3>Make one</h3>
        <ol>
          <li>Click "New Manufacturing Order". It opens in a new tab.</li>
          <li>
            Under "What to Make" pick the "Branch", the "Item" (only items
            with an active BOM are listed), the "Qty" and the "Unit". "BOM
            Version" starts on the item's ★ default version; pick another
            active version if this batch should use it. A job work version
            shows "Job Work For", the customer named on its customer-provided
            items: only that customer's goods are counted for it.
          </li>
          <li>
            Give the "Start Date" and "Due Date", and if you like the "Sales
            Order" it is for, "Materials From" (an area of the branch), "Goods
            Go To", the "Supervisor" and "Notes".
          </li>
          <li>
            "Pack Details" are copied from the item ("MRP (₹)", "USP (₹)" with
            "USP Per", "Batch No", "Best Before") and from the BOM version
            ("Packing Notes"). Change them here for this order; the item and
            the BOM stay as they are. "Pkd Date" starts as the Start Date.
            "Expiry Date" is worked out as the Pkd Date plus the Best Before,
            the day before the period ends (packed 24/11/2026, 18 months:
            23/05/2028); type over it if it should be different.
          </li>
          <li>
            "Materials" lists what the BOM version needs for the quantity,
            marked "BOM": "Required" is the BOM's quantity for the order plus
            its "Loss %". These lines cannot be changed on the order: change
            the BOM, or use "Duplicate as new version". "+ Add material" adds
            an extra line, marked "Added", with its "Per Unit" (for one unit of
            the order), "Loss %" and "Unit". "Free Here" shows what is free in
            the branch after other orders, in red when short. A customer's
            goods can be added only on a job work order for that customer.
          </li>
          <li>
            Click "Save". From now on the order counts its materials as
            "Reserved" and what it makes as "Incoming" in the Stock Check.
            "Cost (Estimate)" at the right shows the materials at today's
            rates.
          </li>
        </ol>
        <h3>Submit and after</h3>
        <p>
          Click "Submit" when the order is final. It gets its number (MO/...)
          and the status "Not Started"; it becomes "In Process" once
          materials are issued and "Completed" when everything is made. A
          submitted order keeps everything except the "Start Date", the
          "Supervisor", the "Notes" and the added materials: those can still
          change until the order is completed or closed (an added material
          never below what was already issued). To change anything else,
          close the order and make a new one. Once an order uses a BOM version,
          that version's materials can no longer change.
        </p>
        <h3>Pick the materials</h3>
        <p>
          The order is its own pick list. On Submit each material gets its
          bins, batches and packages chosen by the same rule as a sales pick
          list: earliest expiry first, then oldest received; Quarantine and
          Rejected batches never; only from "Materials From" (else the whole
          branch); a customer's goods only from that customer's stock. The
          "Pick Materials" box shows each material with what is "Still to
          Issue", what is "Picked" and "Picked From", with a green ✓ or a red
          ✕ and what is short. "Edit picks" opens one material with the
          "Area", "Bin", "Batch" and "Package" pickers (each offers only what
          is free) and the quantity in the stock unit; "+ Add package" adds a
          row and "Done" saves it. "Pick again" proposes a material afresh
          (or all of them, with "Pick again (all materials)"), for example once
          stock comes in. Picked stock is held for the order: other orders,
          pick lists, transfers and Own Use see it as not free until the
          order is cancelled or closed. A material added after Submit is
          picked when the order is saved.
        </p>
        <p>
          "Print ▾" gives the "Manufacturing Order (Batch Sheet)": what to
          make, the Pack Details, the materials and the expected by-products;
          and on a submitted order the "Material Pick List" for the store,
          sorted by bin, with a tick box per row and "Picked By" and "Checked
          By".
        </p>
        <Note>
          "Close MO" ends an open order made short: what is still to make is no
          longer planned and the rest of its materials stop being reserved.
          "Cancel" (with a reason) is allowed only while nothing has been
          issued. Files go in "Attachments" at the right, also after Submit.
        </Note>
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
          purchase invoice, the purchase return and the debit note follow
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
            under it says which store they go to) and the "Expected Delivery"
            date (the date the goods should be received by; an order cannot
            be saved or submitted without it), and if you like the
            "Supplier's Quote Ref".
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
            with no email cannot be ticked. The "Buying Agent" starts as the
            supplier's "Purchaser" in this company (set on the supplier). Change
            it to a broker or firm from the suppliers list (marked "Supplier";
            add it as a supplier first) or to another person ticked "Purchaser"
            in "Masters" › "People" (marked "Purchaser"; type a
            new name and pick 'Create "…"' to add one), or to "None"; then tick
            who of them gets the mail. A purchaser is mailed at their own email,
            else the one they sign in with. Contacts themselves are added on the supplier's ledger.
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
            receipts"); "Purchase Invoice (supplier's bill)" opens a new purchase
            invoice with everything received against the order and not yet
            billed (see "Purchase invoices"). As goods are received the order's status
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
            Tick "Purchase order … (PDF)" under "Attach" to send the order
            with it too.
          </li>
          <li>
            "Email PO" on a submitted order sends the order itself to the
            supplier, as a PDF in the printed layout. "To" starts with the
            contacts ticked "Mail" on the order (and the agent, if ticked),
            "CC" with you; add or remove people as in "Email Supplier". The
            "Subject" reads "Purchase Order No : …" and the message can be
            changed. Click the file name beside "Attached" to see the PDF
            first. "Send" sends it from the company's mail account; replies
            come to you and the order's Activity notes it.
          </li>
          <li>
            Every order mailed with "Email PO" carries a "View and Accept
            Order" button: a private link made for that mailing, which the
            supplier opens without signing in (on a phone or a computer). It
            works for 90 days, and not once the order is cancelled. The
            supplier sees the order and its PDF, gives their name, and clicks
            "Accept Order" (with an expected dispatch date if they like) or
            "Report an Issue" with a comment; they can come back to the same
            link to add a comment. They can never change the order.
          </li>
          <li>
            Each reply comes to you, the Purchase team and the Owner as a
            notice under the bell ("Supplier accepted …", "Supplier issue on
            …"), which opens the order. The order's "Supplier Response" box
            lists each mailing (to whom, by whom, and when the link was
            opened) and each reply, and the orders list has a "Supplier Reply"
            column: "Not sent", "Sent", "Opened", "Accepted" or "Issue".
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
          Every entry screen has an "Attachments" box at the top of the
          column on the right of the page (below the form on a phone or a
          narrow window). Once the order is saved, drop files on it, or click
          "choose files" (or "take a photo" on a phone) to add the supplier's
          challan or invoice, the lorry receipt (LR), the e-way bill, photos and
          other papers: PDF, pictures, Word or Excel, up to 10 MB each. Each file
          shows as a button with its name and type; click one to see it right
          there beside the form, so you can check the paper against the entry
          as you read or type. PDFs and photos show in the page; Word, Excel
          and iPhone (HEIC) photos cannot, so use "Open in New Tab". Under the
          file are who added it and when, "Open in New Tab", "Remove" and its
          "Type" (pick another from the list to change it). Files stay with the
          order after Submit, and more can still be added later. Adding or
          removing a file is written to the order's Activity, which sits below
          in the same column. Anyone who may make orders may add files; others, such as "Storekeeper", only see and open them. If the company has ticked this entry under "Attachment Needed to Submit" (Companies › "Attachments"), "Submit" is refused until at least one file is added; the draft is saved, so add the file and press "Submit" again.
        </p>
        <h3>Transit insurance</h3>
        <p>
          The "Transit Insurance" box says who insures the goods on the way.
          "Insured By" is "Us" when they travel under one of the company's
          marine policies (see the chapter "Insurance policies"), "Supplier"
          when the supplier insures them, or "Not insured". A new order starts
          with "Us" and the policy marked "Default For" purchases, when there
          is one valid on the order date. Under "Us", pick the "Policy"; the
          "Insured Value" is the order total, plus 10% when the policy says
          so, worked out on "Save". A red line warns when the value is above
          the policy's "Limit per Transit" or above the cover left. Submitting
          the order uses up the policy's cover; the goods receipts and purchase
          invoices of the order show the same box, which cannot be changed
          there.
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
          team and the stores (Storekeeper) can both make receipts. A submitted
          receipt's "Create ▾" button makes the "Purchase Invoice (supplier's
          bill)" or a "Purchase Return (goods sent back)". A receipt with goods
          sent back cannot be cancelled until the return is.
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
            "Received By". "Received By" lists the people ticked "Stores" in
            "Masters" › "People", whether or not they sign in to MyERP; type a
            new name and pick 'Create "…"' to add someone.
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
            Each line's bins fold into one line under the item, for example
            "✓ Bins: 600 of 600 Kg" with "2 bins · DC1028 · 15 bags × 40". Click
            "Edit bins" to open that line's bins, and "Done" to fold them
            again. Only one line is open at a time, so a receipt with many
            items stays short.
          </li>
          <li>
            The bins must add up to the "Accepted" quantity, and each bin of a
            batch-tracked item needs its "Batch No". Until then the line shows
            in red, for example "Bins: 264 of 304 Kg · 40 Kg short". "Submit"
            then opens a box listing each such line with "Accepted", "In
            Bins" and "Difference"; "Go to line" takes you to it with its bins
            open. Nothing is submitted, and "Save" still keeps the draft. Fix
            the bin quantities (or the "Received" or "Rejected" quantity if
            that was wrong), then Submit again.
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
            with the supplier's bill.
          </li>
          <li>
            Every item's main item group must have both its "Stock Ledger" and
            its "COGS/Expense Ledger" set for the company. If any are missing,
            Submit opens a box listing each such "Item Group", its "Items" (by
            line) and what is "Missing", all at once. If your role may change
            masters, "Set ledgers" opens that item group in a new tab at its
            "Accounts" box: pick the ledgers, save, and Submit again. If it may
            not, "Ask to set" sends a notice under the bell to everyone whose
            role may change masters, naming the item group, the missing
            ledgers and the receipt, with a link to the item group; the button
            then reads "Asked ✓". Nothing is submitted meanwhile, and the
            draft stays saved.
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
            code printed on the packs matches, and who checked ("Checked By",
            from the same "Stores" people).
          </li>
        </ul>
        <h3>Ledger Posting</h3>
        <p>
          Once a receipt is saved, its "Ledger Posting" box shows the book
          entries: "Ledger", "Ledger Group", "Debit ₹" and "Credit ₹", with a
          total. On a draft it shows what Submit will post, worked out from the
          last "Save" (the strip says "Posts on Submit"); a ledger not set yet
          shows in red, for example "Stock Ledger of item group Tea not set".
          After Submit it shows the entries actually posted ("Posted"), and on
          a cancelled receipt it says they were reversed.
        </p>
        <p>
          A submitted receipt shows "Submitted as … on … at …", its "Ledger
          Posting" and its "Activity".
          A submitted receipt cannot be changed: click "Cancel receipt" and say
          why. Cancelling reverses the stock and the book entries and shows the
          goods as pending on the orders again. It is refused if any of the
          goods have since been issued or moved, including by an entry dated
          later that needed them.
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
          Every entry screen has an "Attachments" box at the top of the
          column on the right of the page (below the form on a phone or a
          narrow window). Once the receipt is saved, drop files on it, or click
          "choose files" (or "take a photo" on a phone) to add the supplier's
          challan or invoice, the lorry receipt (LR), the e-way bill, photos and
          other papers: PDF, pictures, Word or Excel, up to 10 MB each. Each file
          shows as a button with its name and type; click one to see it right
          there beside the form, so you can check the paper against the entry
          as you read or type. PDFs and photos show in the page; Word, Excel
          and iPhone (HEIC) photos cannot, so use "Open in New Tab". Under the
          file are who added it and when, "Open in New Tab", "Remove" and its
          "Type" (pick another from the list to change it). Files stay with the
          receipt after Submit, and more can still be added later. Adding or
          removing a file is written to the receipt's Activity, which sits below
          in the same column. Anyone who may make receipts may add files; others only see and open them. If the company has ticked this entry under "Attachment Needed to Submit" (Companies › "Attachments"), "Submit" is refused until at least one file is added; the draft is saved, so add the file and press "Submit" again.
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
    id: "purchase-invoices",
    title: "Purchase invoices",
    summary:
      "The supplier's bill, entered against goods receipts. Submit books it, with input GST and the due dates.",
    body: (
      <>
        <p>
          A purchase invoice is the supplier's bill. Open it from "Entry" in the
          top menu, then "Purchase", then "Purchase Invoice"; or from a submitted
          goods receipt's or purchase order's "Create ▾" button, "Purchase
          Invoice (supplier's bill)", which fills in what was received and not
          yet billed. "New purchase invoice" starts an empty one: pick the
          "Supplier" and click "Get items".
        </p>
        <p>
          The "Bill Type" at the top says what the bill is for. "Against goods
          receipts" is the usual bill for goods received into stock. "Without
          goods receipt" is for services and for goods not kept in stock (see
          "Bills without goods receipt" below). It is fixed once the bill is
          saved, and from then on shows greyed with a "Locked" tag.
        </p>
        <ul>
          <li>
            "Supplier's Bill": the "Supplier Invoice No" and "Supplier Invoice
            Date" as printed on the bill, and the "Posting Date", which starts as
            the bill date. Change the posting date only when you book a bill on
            another day (a bill of 31 October entered on 2 November, say): it
            decides the month the entries and the GST credit go into. The
            "Credit Term" comes from the order; the due dates count from the
            supplier's invoice date.
          </li>
          <li>
            "Items" lists each receipt line still to bill ("To Bill"), at the
            order's rate. Change "Bill Qty", "Bill Rate" or "GST %" to match the
            bill; a line whose rate differs is shaded and says by how much.
            "Remove" leaves a line for a later bill.
          </li>
          <li>
            "Charges on the Bill" (freight, loading) come from the order. A
            charge ticked "Already in Stock Cost" was added to the goods by the
            receipt, so it only settles against it; an unticked one goes to the
            charge's own expense ledger. "Add charge" adds another.
          </li>
          <li>
            Type the bill's grand total in "Supplier's Bill Total". It shows
            "✓ Matches our total", or our total and the difference. Submit is
            refused until they match; a difference under one rupee goes to Round
            Off. The same supplier invoice number cannot be entered twice for one
            supplier in a year.
          </li>
          <li>
            "Save" keeps a draft; "Entries on Submit" and "Due Dates" then show
            what Submit will post. "Submit" gives the invoice its number and
            posts it: the receipt's value comes out of "Goods Received but Bills
            not Received", GST goes to "Input CGST", "Input SGST" or "Input
            IGST" (made automatically under Duties &amp; Taxes), and the supplier
            is credited with the due dates. If the bill's rate differs from the
            receipt's, the difference goes into the cost of the stock still on
            hand, and the part already used goes to "Purchase Price Difference".
            No stock moves: the receipt brought the goods in.
          </li>
          <li>
            The list shows "Submitted", "Drafts", "Cancelled", "All" and "Goods
            received, not billed": the submitted receipts still waiting for a
            bill, each with "Make Invoice". A first due date already past shows in
            red.
          </li>
          <li>
            "Cancel invoice" asks why, reverses the entries and makes the goods
            "not billed" again. It is refused once stock it revalued has been
            used since. A billed goods receipt cannot be cancelled until its
            invoice is, and an invoice with a debit note against it cannot be
            cancelled until the debit note is.
          </li>
          <li>
            "Create ▾" on a submitted invoice makes a "Debit Note (goods sent
            back)" for goods returned on a Purchase Return and billed on this
            invoice, a "Debit Note (rate charged higher)" when the supplier
            agrees a lower price afterwards, or a "Supplementary Bill (rate
            charged lower)" when the supplier charges more afterwards. The
            invoice's "Later Changes" lists them, and it cannot be cancelled
            while they stand.
          </li>
          <li>
            <b>Bills without goods receipt.</b> Pick "Without goods receipt" as
            the "Bill Type". Under "Items and Services", each line picks an item
            (a service, or goods with "Maintain stock" off) or an expense ledger,
            such as "Courier Charges". An item brings its HSN or SAC code, unit
            and GST rate, and is booked to the "Expense Account" on its item
            master (shown in "Booked To"); a ledger is booked to itself, and you
            type its SAC code. Only expense ledgers are offered: fixed assets are
            not bought on this bill, and items kept in stock need a goods receipt
            first. "Add line" adds another. Submit debits each line's ledger and
            the input GST and credits the supplier, with the due dates. No stock
            moves. The list shows these bills with a "No GRN" tag.
          </li>
          <li>
            A supplementary bill lists every line of the original bill at the
            quantity billed and kept. Type the "Revised Rate" on the lines whose
            price went up, the supplier's "Supplier Invoice No" and "Supplier
            Invoice Date", and the "Supplier's Bill Total". "Submit" credits the
            supplier with due dates from the original's credit term, counted
            from this bill's date, books the extra input GST, and adds the extra
            to the cost of the stock still on hand; the part for goods already
            used goes to "Purchase Price Difference". No quantity moves. It shows
            in the list with a "Supplementary" tag and is cancelled like any
            invoice.
          </li>
          <li>
            The "Attachments" box, at the top of the right-hand column, keeps the
            supplier's bill (PDF or photo) and any other papers, on the draft and
            after Submit. Click a file's name to see it beside the invoice, so the
            bill can be checked line by line without leaving the page.
            If the company has ticked this entry under "Attachment Needed to Submit" (Companies › "Attachments"), "Submit" is refused until at least one file is added; the draft is saved, so add the file and press "Submit" again.
          </li>
          <li>
            <b>TDS.</b> Every purchase bill (against goods receipts, without goods
            receipt, and supplementary bills) has a "TDS" box once it is saved.
            Each line gets a TDS section: from the "TDS Section" on its item or
            expense ledger; for goods, "194Q" when the company ticks "Deduct TDS
            on purchase of goods (194Q)"; otherwise the supplier's "Default TDS
            Section". On a draft you can change or clear a line's "Section" in the
            box; it is saved at once and kept when the bill is saved again.
            MyERP takes the section's rates and limits from the central "TDS
            Sections" list as on the bill's date and works TDS out on the amount
            before GST ("On ₹ (Before GST)"): a bill whose lines in a section pass
            the one-bill limit deducts, and so does a bill that takes the
            supplier's year (this company, this financial year, shown as
            "Supplier's Year So Far") past the year limit, which then also
            catches up the earlier bills that did not deduct. 194Q deducts only
            on what passes ₹50,00,000. The rate follows the "Deductee Type"
            (from the supplier, else read from its PAN); a supplier without a PAN
            pays the higher "No PAN" rate. TDS is rounded to the rupee, and
            "Why" says how each line was worked out. On a bill dated 1 April
            2026 or later a section shows its Income-tax Act 2025 number first,
            with the old one in brackets, as "393(1) Sl. 6(i) (194C)"; an older
            bill keeps "194C". The section pickers show both numbers, so typing
            either finds it. A supplier abroad has no TDS
            here. Submit credits "TDS Payable 194C" (one ledger per section, made
            under Duties &amp; Taxes the first time) and credits the supplier
            with the bill total less TDS; the due dates split that net amount.
            Paying TDS to the government (challan), the 26Q return and Form 16A
            come in later pieces of work.
          </li>
          <li>
            "Print ▾" prints the page or saves it as a PDF. "Scan e-invoice QR",
            bills before the goods come and imports' bills come in later pieces
            of work.
          </li>
        </ul>
        <Note>
          Invoices are made and submitted by the Purchase role; cancelling needs
          an Owner or a role with "cancel" for purchase. The posting date must
          fall in an open month of a fiscal year.
        </Note>
      </>
    ),
  },
  {
    id: "purchase-returns",
    title: "Purchase returns",
    summary:
      "Goods sent back to the supplier against a goods receipt. Submit takes them out of stock.",
    body: (
      <>
        <p>
          A purchase return records goods sent back to the supplier, for
          example 3 of 200 boxes that came damaged. Open it from "Entry" in the
          top menu, then "Purchase", then "Purchase Return"; or from a submitted
          goods receipt's "Create ▾" button, "Purchase Return (goods sent
          back)". The Purchase team and the stores can both make returns.
        </p>
        <ul>
          <li>
            "Return Details": pick the "Goods Receipt" (the supplier comes from
            it), the "Return Date", the "Reason" ("Damaged in transit", "Short
            supplied", "Quality rejected", "Wrong item" or "Other"), and how the
            goods go back: "Transporter" ("By Supplier" when the supplier
            collects), "Vehicle No", "LR / Docket No" and "E-way Bill No".
          </li>
          <li>
            "Items Going Back" lists every line of the receipt, one row for each
            bin and batch it was put in, at 0. Type the "Return Qty". It cannot be
            more than was received less what went back before, nor more than is
            still in that bin. "Value ₹" is the quantity at the receipt's rate.
          </li>
          <li>
            "Save" keeps a draft and shows "Entries on Submit". "Submit" gives
            the return its number, takes the goods out of the bin (from the
            receipt's own stock first) and moves their value out of "Goods
            Received but Bills not Received" and the item group's stock ledger.
            If the goods' cost has changed since they came in, the difference
            goes to "Purchase Price Difference". The supplier's account and GST
            are not touched: the Debit Note does that.
          </li>
          <li>
            Once the supplier's bill is in, "Create ▾" › "Debit Note" makes the
            debit note for these goods. If the bill leaves the returned goods
            out (it was made for 197, say), no debit note is needed and the
            receipt is settled when that bill is entered.
          </li>
          <li>
            "Cancel return" asks why, puts the goods back into the bins they
            left and reverses the entries. It is refused while a debit note
            settles the return; cancel the debit note first.
          </li>
          <li>
            The "Attachments" box keeps photos of the damage, the return challan
            and other papers, on the draft and after Submit.
          </li>
          <li>
            "Print ▾" › "Return Challan" prints the page to go with the goods, or
            saves it as a PDF.
          </li>
        </ul>
        <Note>
          The return date cannot be before the receipt date and must fall in an
          open month of a fiscal year. Cancelling needs an Owner or a role with
          "cancel" for purchase or stock.
        </Note>
      </>
    ),
  },
  {
    id: "debit-notes",
    title: "Debit notes",
    summary:
      "Goods sent back, debited against the supplier's bill at the bill's rate and GST.",
    body: (
      <>
        <p>
          A debit note takes off the supplier's bill the goods you sent back on a
          purchase return. For example: 200 boxes received, 3 damaged and
          returned, the supplier bills all 200: enter the bill for 200, then a
          debit note for the 3. Open it from "Entry" in the top menu, then
          "Purchase", then "Debit Note"; or from "Create ▾" on a submitted
          purchase invoice or purchase return.
        </p>
        <p>
          When the bill deducted TDS, the debit note takes back TDS in
          proportion to what it debits: "TDS Payable" is debited for that
          share and the supplier's balance goes down by the note less it.
        </p>
        <p>
          With the "Reason" "Rate charged higher" a debit note instead takes a
          lower agreed price off goods already billed (no return needed). Make
          it from the invoice's "Create ▾" › "Debit Note (rate charged higher)".
          Every line of the bill is listed at the quantity billed and kept;
          type the "Agreed Rate" on the lines whose price came down (lower "Qty"
          if only part gets the new rate). "Submit" debits the supplier,
          reverses that much input GST and takes the difference off the cost of
          the stock still on hand; the part for goods already used goes to
          "Purchase Price Difference". No quantity moves. A higher price needs a
          Supplementary Bill instead (see Purchase invoices).
        </p>
        <ul>
          <li>
            "Debit Note Details": "Against Invoice" is the supplier's bill (the
            supplier comes from it), the "Debit Note Date", the "Reason" ("Goods
            returned") and, if the supplier sends its own credit note, "Supplier's
            Credit Note No" and "Supplier's Credit Note Date".
          </li>
          <li>
            "Items" lists each returned line billed on that invoice and not yet
            debited ("Returned, Not Debited"). "Qty" starts at all of it; it can
            be lowered, not raised. Rate and GST come from the bill.
          </li>
          <li>
            "Totals" works out GST line by line and rounds the total to the rupee.
          </li>
          <li>
            "Save" keeps a draft and shows "Entries on Submit" and "Bill Due After
            This Note". "Submit" gives the note its number and posts it: the
            supplier is debited (what we owe on that bill goes down), "Goods
            Received but Bills not Received" is cleared for the returned goods,
            and "Input CGST", "Input SGST" or "Input IGST" is reversed. If the
            bill's rate differs from the receipt's, the difference goes to
            "Purchase Price Difference". No stock moves: the return already took
            the goods out.
          </li>
          <li>
            "Bill Due After This Note" shows the bill's due dates less its debit
            notes, taken off the latest due date first.
          </li>
          <li>
            "Cancel debit note" asks why and reverses the entries; the returned
            goods show as not debited again.
          </li>
          <li>
            The "Attachments" box keeps the supplier's credit note and other
            papers. "Print ▾" prints the page or saves it as a PDF.
          </li>
        </ul>
        <Note>
          Debit notes are made and submitted by the Purchase role. The date must
          fall in an open month of a fiscal year.
        </Note>
      </>
    ),
  },
  {
    id: "tds-check",
    title: "TDS check and TDS adjustments",
    summary:
      "Check each supplier's TDS for the year, and put right a bill where TDS was missed or is wrong.",
    body: (
      <>
        <p>
          Run the TDS Check before each quarter's TDS return. Open it from
          "Entry" in the top menu, then "Accounts", then "TDS Check". It works out again every
          submitted purchase bill of the "Financial Year", supplier by
          supplier and in date order, with today's masters: the "TDS Section"
          on the item or ledger (or the supplier's "Default TDS Section"), the
          supplier's PAN and "Deductee Type", and the section's rates and
          limits on the bill's date. A section chosen by hand on a bill stays
          as chosen. So a bill entered before its item had a TDS Section shows
          up here. Such a bill also counts in the supplier's "Year So Far" on
          later bills: a goods bill entered before its items had 194Q still
          counts towards the year's ₹50,00,000, even though no TDS was due on
          it. With "Show" at "Only with something to put right" a supplier
          below the limit with its sections all on its bills is not listed;
          pick "All suppliers" to see it as "Below limit".
        </p>
        <ul>
          <li>
            The list has one line per supplier ledger and section: "Bills",
            "Before GST ₹", "TDS Due ₹", "TDS Deducted ₹" (on the bills, plus
            submitted TDS Adjustments), "Short (Excess) ₹", "No Section On Bill"
            and "Result": "Short", "Excess", "Section missing", "Matches" or
            "Below limit". "Section missing" means no TDS is owed, but bills had
            no section (or another one) when billed, because the item or ledger
            got its section later. "Show" picks "Only with something to put
            right" or "All suppliers"; each column has its own search. "Check
            Again" runs it afresh.
          </li>
          <li>
            Double-click a line (or click it, then "Open") to see that
            supplier's bills one by one in a new tab: "Year So Far ₹", "Section
            On Bill", "TDS Due ₹", "Deducted ₹", the gap and "Why".
          </li>
          <li>
            "Put It Right" shows what can be put right. "Make TDS Adjustment"
            (or "Set Section", when only sections are missing) opens a new TDS
            Adjustment for those bills in a new tab.
          </li>
          <li>
            "TDS Returns" lists the year's four quarters. When a quarter's
            return is filed, click "Mark Filed" and give "Filed On" and the
            "Acknowledgement No". From then on that quarter's bills cannot be
            adjusted, an adjustment cannot be dated in it or cancelled from it,
            and its bills with TDS cannot be cancelled. Only an Owner can
            "Remove mark" if it was marked by mistake.
          </li>
        </ul>
        <p>
          <b>TDS Adjustment.</b> A submitted bill is never changed, so a gap is
          put right on a TDS Adjustment (also under "Entry" › "Accounts" ›
          "TDS Adjustment", which lists them). "Date" is the day the TDS is
          deducted. "Bills Covered" lists each bill with "TDS On ₹", "Rate %",
          "TDS Due ₹", "Deducted ₹" and "This Adjustment ₹", the gap the TDS
          Check finds; it cannot be typed and is worked out again on "Submit".
          Untick a bill to leave it out. For TDS missed, "Months Late" and
          "Interest ₹" show the interest for deducting late (a month or part of
          one, from the bill's date), to pay with the TDS challan; it is not
          posted.
        </p>
        <ul>
          <li>
            "Save" keeps a draft and shows "Ledger Posting". "Submit" gives it
            its number and posts it. TDS missed ("Deduct short TDS"): the
            supplier is debited and "TDS Payable" for the section credited, so
            the supplier owes that much (or is paid that much less). TDS
            deducted in excess ("Give back excess TDS"): the other way; use it
            only while that TDS is not yet paid to the government.
          </li>
          <li>
            A section missed on a bill that owes nothing ("Set section only"):
            the bill's line shows "Section only" at ₹0, and nothing is posted.
            The adjustment records the section against the bill, so it counts
            under that section from then on. A bill that is short gets its
            section recorded by the same adjustment that deducts the TDS.
          </li>
          <li>
            The bill's own "TDS" box then lists "TDS adjusted later" with the
            adjustment's number (or "Section … set later" for a ₹0 one, with
            the date and who submitted it), and "Total TDS on This Bill", so the
            bill shows
            all the TDS deducted against it (payment advices to suppliers will
            show the same).
          </li>
          <li>
            "Cancel adjustment" asks why and reverses the entries; the bills show
            their gap (or missing section) again. A bill named on a submitted adjustment cannot be
            cancelled until the adjustment is.
          </li>
          <li>
            The "Attachments" box keeps working papers. "Print ▾" prints the page
            or saves it as a PDF.
          </li>
        </ul>
        <Note>
          The TDS Check and TDS Adjustments are for roles that may see the books
          (Accountant, Owner); "Mark Filed" needs the right to submit accounts
          entries. The interest rate and the treatment of excess TDS are to be
          confirmed by the CA.
        </Note>
      </>
    ),
  },
  {
    id: "sales-orders",
    title: "Sales orders",
    summary:
      "What a customer asks the company for: the rate it pays, where the goods go out from, stock on hand, and the order confirmation mail.",
    body: (
      <>
        <p>
          A sales order says what a customer asked for, at what rate and by
          when. It is the first step of sales: the pick list, the delivery note
          and the sales invoice follow from it. A sales order posts nothing to
          the books or to stock.
        </p>
        <h3>Find the sales orders</h3>
        <p>
          Click "Entry" in the top menu, point at "Sales" and click "Sales
          Order". "Entry" shows the sales part only when the company picked at
          the top right uses the Sales module and your role may see sales. The
          list works like the purchase order list: "Open (drafts and ordered)"
          shows first, every column has its own "Search" box, and clicking an
          order shows its details at the right with "Open" and "Print".
        </p>
        <h3>Make a sales order</h3>
        <ol>
          <li>Click "New sales order" (it opens in a new browser tab).</li>
          <li>
            Under "Customer and Dates" pick the "Customer". The line under it
            shows its GSTIN, what it owes now ("Outstanding") and its credit
            limit. A new customer can be made with 'Create "…"', which opens the
            "Add ledger" form under "Sundry Debtors". The customer's "Salesman",
            "Credit Term" and "Transporter" fill in by themselves; you can
            change them for this order. "Transporter" is "By Customer" when the
            customer collects the goods.
          </li>
          <li>
            Fill in the "Order Date" and the "Delivery Date" (the date the
            customer wants the goods by; an order cannot be saved without it),
            and if you like the "Customer's PO No" and "Customer's PO Date".
          </li>
          <li>
            Pick "Despatch From": a branch, or one area of a branch (shown as
            "Branch › Area", with how many racks it has). With an area picked,
            stock is counted only in that area and the racks and bins in it;
            with a branch, in the whole branch. Branches that keep no stock are
            not offered.
          </li>
          <li>
            Under "Addresses", "Bill From" starts as the despatch branch. Pick
            the "Customer Billing Address" and the "Ship To" address from the
            customer's addresses (its billing and shipping ones to start with).
            The billing address's state decides the GST: the same state as
            "Bill From" gives CGST + SGST, another state IGST. An overseas
            customer pays no GST.
          </li>
          <li>
            Under "Customer Contacts" tick who gets the order confirmation by
            mail. The main contact and the sales contacts are ticked to start
            with.
          </li>
          <li>
            Under "Items" pick each item. Only items the customer may buy are
            offered (as set on the customer's "Products" tab). The "Unit"
            starts as the item's sales unit; you can pick any other unit of the
            item, and no other. The "Rate" fills in by itself, with where it
            came from under it: first the customer's own price, then its price
            list, and last the item's MRP ("MRP (no price set)"). Type another
            rate to change it. "In Stock" shows what is at the "Despatch From"
            place, in the line's unit; it turns red when the quantity ordered
            is more than that.
          </li>
          <li>
            Under "Charges" add freight, packing or other charges billed to the
            customer. Each is a service item ticked "Use as Sales Charge" in
            the Items master (in the "Switches" panel).
          </li>
          <li>
            Under "Terms and Notes" the customer's own set of sales terms (else
            the company's default) fills in; change the text if needed. The
            "Internal Note" is not printed. Add files under "Attachments".
          </li>
          <li>
            Click "Save" to keep a draft (the page stays open) or "Submit" to
            give the order its number. "Close" closes the tab.
          </li>
        </ol>
        <h3>Credit limit</h3>
        <p>
          When what the customer owes plus this order is more than its credit
          limit, a note says so at the top of the form and of the order. It is
          a warning only: the order can still be saved and submitted.
        </p>
        <h3>After Submit</h3>
        <p>
          The order's page says "Submitted as …" with the date and time.
          "Email Customer" mails the order confirmation, with the order as a
          PDF, to the ticked contacts; a copy goes in the order's Activity.
          "Print ▾" holds "Sales order" and "Download PDF". Submit also makes
          the order's pick list (see "Pick lists"): a note at the top says
          whether every item was found in stock, with "Open Pick List", and
          the boxes under it count the pick lists, delivery notes and
          invoices made from the order. "Create ▾" holds "Pick List" (a new
          one, when the order has none that is open or picked) and "Delivery
          Note" (once the pick list is submitted; see "Delivery notes"); the
          Sales Invoice joins it when it is built. The "Delivered" box shows, per item, what was ordered, sent
          and still to go; "Close Line" (with a reason) closes a balance that
          will not be sent, and "Reopen Line" opens it again. "Cancel order"
          (with a reason) works on a draft or an order nothing has gone
          against, and cancels its pick list too. "Duplicate" makes a new
          draft from the order.
        </p>
        <h3>Purchase orders for shortages</h3>
        <p>
          Submit also runs the Stock Check (see "Stock Check") for the order's
          items at its branch, with this order now counted in "Reserved". An
          item the branch buys that falls below its safety stock gets a draft
          purchase order to its Preferred Supplier, filled up to "Order Up
          To", one order per supplier. An item with no Stock Planning line
          there but "Main Fulfilment" Purchase is bought for the shortage
          only. An item the branch gets by transfer gets a draft stock transfer
          from its source branch, one per source, in its sales unit; the box
          "Stock Transfers" counts them. Goods already on order or on the way,
          drafts included, count as "Incoming", so they are not ordered again. The note "Shortages planned on
          Submit" lists each item that is short and what was done; the box
          "Purchase Orders" counts the drafts made for the order. In "Items",
          "Expected" shows what the branch will have once its orders go out and
          come in, and "Covered By" shows the draft purchase order or "Draft
          ST" (the stock transfer), "To make"
          for an item the branch manufactures (Manufacturing Orders come
          later), or "In stock". The drafts are not sent: someone in Purchase
          checks each one and submits it. When the order changes, or a draft
          was cancelled, "Create ▾" then "Purchase Orders for Shortages" runs
          the check again. Cancelling the sales order leaves its drafts for
          you to cancel or keep.
        </p>
      </>
    ),
  },
  {
    id: "pick-lists",
    title: "Pick lists",
    summary: "Which bin and batch the stores take a sales order's goods from: made on Submit, changed while open, final once submitted.",
    body: (
      <>
        <p>
          A pick list tells the stores where to take an order's goods from:
          the bin, the batch and how much, item by item. It is made by itself
          when a sales order is submitted. It posts nothing to the books or to
          stock; the delivery note moves the goods.
        </p>
        <h3>How the bins and batches are chosen</h3>
        <ul>
          <li>
            Only places in the order's "Despatch From": the area and the racks
            and bins in it, or the whole branch.
          </li>
          <li>Earliest expiry first, then the oldest received.</li>
          <li>
            Where a bin holds numbered packages (the PK numbers from the goods
            receipt), each is taken whole, lowest number first; only the last
            one an item needs is opened. Stock without package numbers shows
            "No package".
          </li>
          <li>A batch held back ("Quarantine" or "Rejected") is never picked.</li>
          <li>
            Stock on another open or picked pick list is kept aside, so two
            orders never pick the same bags. A package on another list is not
            offered at all.
          </li>
        </ul>
        <p>
          When not enough is found, the list picks what there is and the
          note at the top says "Not all in stock", with what was ordered,
          found and short for each item. The same note shows on the sales
          order.
        </p>
        <h3>Find the pick lists</h3>
        <p>
          Click "Entry", point at "Sales" and click "Pick List", or click
          "Open Pick List" on the sales order. The list shows "Open" lists
          first; pick "Picked", "Cancelled" or "All" in the box above it.
          Every column has its own "Search" box. Click a list to see it at the
          right, with "Open" and "Print".
        </p>
        <h3>Change an open list</h3>
        <p>
          Click "Edit". Each item shows its rows with "Area", "Bin", "Batch",
          "Package" and "Pick Qty (Stock Unit)". Each picker offers only what
          is free in the one before it: the areas of the Despatch From branch,
          the bins in that area, the batches in that bin and the packages of
          that batch, each with how much is free. Change a row, remove it with
          ✕, or click "+ Add package" to take some from another bag or bin.
          "Still Short" shows what is left. Click "Save"; a row asking for
          more than is free, a package on another list, or a line picking
          more than was ordered, is refused with the reason.
          "Discard changes" leaves the list as it was.
        </p>
        <h3>Pick from another branch</h3>
        <p>
          When the goods are not where the order said, an open list can pick
          from somewhere else. Open "Despatch From" on the list. The picker
          lists every branch that keeps stock, and the areas in each, with how
          many of the order's items each place holds in full ("1 of 1 items
          ✓"); the order's own place is marked "(the order's)". Pick one and
          click "Pick again from …": the bins and batches are chosen again by
          the same rule, in that place only, and the tag at the top shows the
          new place. The sales order's "Bill From" and tax do not change; the
          delivery note sends the goods from the pick list's branch. One list
          takes from one branch, and once it is submitted its place is fixed.
        </p>
        <h3>Submit, print and cancel</h3>
        <p>
          When the goods are picked, click "Submit": the list is "Picked" and
          final. "Print ▾" holds "Pick list" and "Download PDF". The print is
          an A4 sheet for the stores: the list's number with its barcode, the
          sales order, customer, Despatch From, delivery date and transporter,
          then the rows bin by bin so the picker walks rack by rack. Each bin
          is printed large with its barcode (the same code as on the bin
          sheets), then the item, batch and expiry, the package number with
          its barcode (as on the bag label; a bag to open says "OPEN: take 4
          of 10"), the quantity to pick in
          the order's unit, a box to tick and a space to write what was
          picked. Anything not found is listed under "Short: not found in
          stock", and the foot has "Picked By", "Checked By" and "Date and
          Time" lines to sign. "Cancel" (with a
          reason) frees the stock the list kept aside; then "Create ▾ › Pick
          List" on the sales order makes a new one. Files go under
          "Attachments". Who may see or change pick lists: people whose role
          may see or make sales or stock entries. Once a delivery note made
          from the list is submitted, the list is "Delivered".
        </p>
      </>
    ),
  },
  {
    id: "delivery-notes",
    title: "Delivery notes",
    summary: "The goods going out to the customer: made from a picked pick list, takes the stock out of its bins and posts its cost.",
    body: (
      <>
        <p>
          A delivery note is the goods leaving for the customer. It is made
          from a pick list once the list is submitted ("Picked"), and starts
          with every bin, batch and quantity the stores picked. On Submit the
          goods leave their bins and the order counts them as delivered.
        </p>
        <h3>Make one</h3>
        <ol>
          <li>
            On the submitted pick list, or on the sales order, click "Create ▾"
            and "Delivery Note". The note opens in a new tab as a draft. Doing
            it again opens the same draft.
          </li>
          <li>
            "Customer and Despatch" shows the customer, the "Despatch From",
            the order, "Bill From", "Ship To" and the customer's PO, all from
            the order. Set the "Note Date" (not before the order date).
          </li>
          <li>
            Under "Transport (for the e-way bill)" fill in the "Transporter"
            (from the order; "By Customer" if the customer collects), "Mode",
            "Vehicle No", "Distance (km)", "LR / Docket No", "LR Date",
            "Packages" and "Gross Weight (kg)". The e-way bill is made with
            the sales invoice from these.
          </li>
          <li>
            "Items" shows each line with "Ordered", "Sent Earlier", "Picked",
            "This Note", the order's "Rate" and the "Taxable" value. Click
            "▸ 1 bin" (or "2 bins") to open the line's bins: lower "Send" to
            send less, or click "+ Another bin" to send from another bin or
            batch that has the stock free. What is not sent stays pending on
            the order. "Done" folds the bins again. A red ✕ means the line
            sends more than is still to go.
          </li>
          <li>
            Add the signed challan or photos under "Attachments" (they can
            also be added after Submit).
          </li>
          <li>
            Click "Save" to keep the draft, or "Submit". The page stays open
            and says "Submitted as …" with the date and time.
          </li>
        </ol>
        <h3>When Submit is refused</h3>
        <p>
          Everything that stops it shows in one popup, each with "Go to line":
          a bin that no longer has the stock (another entry took it since it
          was picked), a batch held back ("Quarantine" or "Rejected"), or a
          line sending more than is pending. If the item group's ledgers are
          not set, the popup lists them with "Set ledgers" (or "Ask to set"
          for someone who may not change masters), as on the goods receipt.
          The draft is kept.
        </p>
        <h3>What it posts</h3>
        <p>
          The "Ledger Posting" box shows, on a draft, what Submit will post
          and, once submitted, what was posted: the cost of the goods by FIFO
          (oldest stock first) is debited to "Goods Delivered but Bills not
          Made" and credited to the item group's "Stock Ledger". It is at
          cost, not at the sale price. The sales invoice later moves the cost
          to the "COGS/Expense Ledger" and books the sale and GST.
        </p>
        <h3>After Submit</h3>
        <p>
          The sales order shows the quantities under "Delivered" and
          "Pending" and turns "Part delivered" or "Delivered"; its "Delivery
          Notes" box counts the notes. For what is still pending, "Create ▾ ›
          Pick List" on the order picks it. Each package sent becomes "Used
          up", or "Part used" with what is left in it, so the bin contents
          and bag counts stay true. "Print ▾" holds "Delivery
          Challan" (items, HSN, quantities, values and GST, with the
          transport), "Packing List" (bins, batches and packages, with a "Checked"
          column) and "Download PDF". "Create ▾ › Sales Invoice" makes the
          note's invoice (see Sales invoices); the note then shows "Billed on"
          with the invoice number. A billed note cannot be cancelled until its
          invoice is cancelled. "Cancel Note" (with a reason) puts the
          goods back in their bins and packages, reverses the entries and makes the
          order's quantities pending again; the pick list is "Picked" again.
        </p>
        <h3>Stock never goes below zero</h3>
        <p>
          No entry can take out more than a bin (and batch) holds. The check
          uses the stock on the entry's own date, so a note dated in the past
          is checked against what was there that day, and it may not take
          goods that a later entry already sent out. If it would, Submit is
          refused with "… is already taken by later entries", naming the day
          the stock would run short: date the note later or cancel the later
          entry first. The same holds for purchase returns and for cancelling
          a receipt. When two people submit from the same stock at the same
          moment, the second waits for the first and is then checked against
          what is left.
        </p>
        <h3>Find the delivery notes</h3>
        <p>
          Click "Entry", point at "Sales" and click "Delivery Note". Pick
          "Draft", "Submitted", "Cancelled" or "All" in the box above the
          list; every column has its own "Search" box. Click a note to see it
          at the right with "Open" and "Print". Who may see or make delivery
          notes: people whose role may see or make sales or stock entries.
        </p>
      </>
    ),
  },
  {
    id: "sales-invoices",
    title: "Sales invoices",
        summary: "The tax invoice for one or more delivery notes: books the sale and GST, gives the e-invoice JSON and keeps the e-invoice and e-way bill numbers.",
    body: (
      <>
        <p>
          A sales invoice is the tax invoice for the goods on one or more
          submitted delivery notes of a customer, so several despatches can go
          on one invoice and one e-invoice. Its quantities are what the notes
          sent; its rates, charges and credit term are the sales order's and
          cannot be changed on the invoice. On Submit it gets its number from
          the "Sales invoice" series of the "Bill From" branch and books the
          sale.
        </p>
        <h3>Make one</h3>
        <ol>
          <li>
            On the submitted delivery note click "Create ▾" and "Sales
            Invoice". The invoice opens in a new tab as a draft. Doing it
            again opens the same draft.
          </li>
          <li>
            "Customer and Billing" shows the customer and GSTIN, "Bill From",
            "Place of Supply", "Bill To", "Ship To", the customer's PO and the
            salesman, from the order and the note. Set the "Invoice Date" (not
            before the delivery note's date).
          </li>
          <li>
            "Delivery Notes" lists the notes on the invoice. To bill more of
            the customer's notes on it, click "Add Delivery Notes": it lists
            the customer's other notes not billed yet that go from the same
            place to the same address on the same credit term; click "Add" on
            each, and "Done". "Remove" takes a note off again (one must stay).
            Adding or removing a note saves the draft.
          </li>
          <li>
            "Payment" shows the "Credit Term" from the order and the due dates,
            which split the total by the term, counted from the invoice date.
          </li>
          <li>
            "Items" lists the notes' lines with "Qty", "Unit", "Rate",
            "Taxable", "GST %", "GST" and "Amount", at the order's rates. With
            several notes each line names its note under the item.
          </li>
          <li>
            "Charges" has the order's charges (freight, packing) on the
            order's first invoice. A "% of items" or "Per unit" charge counts
            what is billed on this invoice.
          </li>
          <li>
            "Transport (for the e-way bill)" comes from the delivery note:
            "Transporter", "Mode", "Vehicle No", "Distance (km)", "LR / Docket
            No" and "LR Date".
          </li>
          <li>
            The "Totals" panel on the right shows the taxable value, CGST and
            SGST (same state) or IGST (another state), the round off and the
            total. Add files under "Attachments", at the top of the right
            column.
          </li>
          <li>
            Click "Save" to keep the draft, or "Submit". The page stays open
            and says "Submitted as …" with the date and time.
          </li>
        </ol>
        <h3>When Submit is refused</h3>
        <p>
          If an item group has no "Sales Ledger" (or "COGS/Expense Ledger")
          for the company, a popup lists the groups with the lines and
          charges that need them, with "Set ledgers" (it opens the item group
          at its "Accounts" box) or "Ask to set" for someone who may not
          change masters. The draft is kept.
        </p>
        <h3>What it posts</h3>
        <p>
          The "Ledger Posting" box shows, on a draft, what Submit will post
          and, once submitted, what was posted: the customer is debited with
          the total; each item group's "Sales Ledger" is credited with its
          items and charges; "Output CGST" and "Output SGST" (or "Output
          IGST") with the tax; "Round Off" with the rounding to the rupee.
          The cost the delivery note set aside in "Goods Delivered but Bills
          not Made" moves to the item group's "COGS/Expense Ledger".
        </p>
        <h3>e-Invoice and e-Way Bill</h3>
        <p>
          A submitted invoice has the "e-Invoice and e-Way Bill" box at the
          top. For a registered customer (or an SEZ or an export) click
          "Download e-Invoice JSON" and upload the file on the government
          e-invoice portal; with the transport details filled in, the portal
          makes the e-way bill with it. Then click "Enter Portal Numbers" and
          either click "Read Portal File" and pick the JSON file the portal
          gives back (it fills everything below), or type the "IRN", "Ack
          No", "Ack Date", the "Signed QR Code" (paste it), the "e-Way Bill
          No", "e-Way Bill Date" and "Valid Until"; click "Save". The signed
          QR code prints at the top right of the invoice; until it is in,
          that place says the QR code prints there once the IRN is entered. The
          portal makes the e-way bill with the e-invoice only for goods. A
          job-work service billed under its SAC carries the item's "Delivery
          HSN" on the "e-Way Bill" print; for an invoice of services alone,
          make the e-way bill on the e-way bill portal under that code. A link to the portal
          that does this by itself comes later.
        </p>
        <p>
          "Update Transport" changes the transporter, mode, vehicle, distance
          and LR even after Submit, as they post nothing. Until the portal is
          linked, make the same change on the e-way bill portal too.
        </p>
        <h3>After Submit</h3>
        <p>
          The delivery note shows "Billed on" with the invoice. The print
          shows our "Bill From" address with GSTIN and FSSAI, the customer's
          address with GSTIN, FSSAI and contact, the ship-to address, and the
          terms and conditions of the sales order (else the customer's or
          the company's default sales terms). "Print ▾" holds
          "Tax Invoice (Original for Recipient)", "Tax Invoice (3 copies:
          Original, Duplicate, Triplicate)", "e-Way Bill" and "Download PDF".
          "Create ▾" holds "Credit Note" (see "Credit notes"); the receipt
          comes later. On the right, "Credit Notes" lists the notes made
          against the invoice. "Cancel Invoice" (with a reason) reverses the
          entries; its delivery notes can then be billed again. An invoice
          with a submitted credit note cannot be cancelled until the note is.
          If the e-invoice was made, cancel it on the portal too (allowed
          within 24 hours).
        </p>
        <h3>Find the sales invoices</h3>
        <p>
          Click "Entry", point at "Sales" and click "Sales Invoice". Pick
          "Draft", "Submitted", "Cancelled" or "All" in the box above the
          list; every column has its own "Search" box, and "e-Invoice" shows
          "Pending" for an invoice still to be uploaded. Click an invoice to
          see it at the right with "Open" and "Print". Who may see or make
          sales invoices: people whose role may see or make sales entries.
        </p>
      </>
    ),
  },
  {
    id: "credit-notes",
    title: "Credit notes",
    summary:
      "A GST credit note against a sales invoice: goods coming back, goods not coming back, or a rate difference.",
    body: (
      <>
        <p>
          A credit note lowers what a customer owes on a sales invoice, with
          its GST. It has one of three types, picked under "Type":
        </p>
        <ul>
          <li>
            "Sales Return – goods come back": the customer sends goods back.
            They go back into stock, in the same batch they went out in, into
            the bin you pick, at the cost they left at.
          </li>
          <li>
            "Sales Return – goods not coming back": the customer keeps or
            destroys the goods (damaged, short received) and is credited as for
            a return. No stock moves.
          </li>
          <li>
            "Rate Difference": the customer is charged a lower rate on what was
            billed. No stock moves.
          </li>
        </ul>
        <p>
          All three take the rate, GST and place of supply from the invoice and
          share one number series ("Credit note" in the company's numbering),
          as GST needs.
        </p>
        <h3>Make one</h3>
        <ol>
          <li>
            On the submitted sales invoice click "Create ▾" and "Credit Note".
            The credit note opens in a new tab as a draft. While a draft is
            open for that invoice, doing it again opens the same draft.
          </li>
          <li>
            In "Credit Note Details" pick the "Type". Changing it shows
            "Change Type", which starts the lines again from the invoice.
            Set the "Credit Note Date" (not before the invoice), the "Reason",
            and if you like the "Customer's Ref" (their return or debit note
            number) and "Remarks".
          </li>
          <li>
            For a sales return, "Items" lists every invoice line with
            "Billed" and "Already Returned"; type the "Return Qty". For goods
            that come back there is one line per batch that went out, and
            "Into Bin" (from the bin it went out of; pick another, such as a
            returns bin, if you like). The quantity cannot be more than went
            out less what earlier credit notes returned.
          </li>
          <li>
            For a rate difference, "Items" lists the "Billed Qty" (less what
            was returned) and the "Bill Rate ₹"; type the "Correct Rate ₹".
            "Less / Unit ₹" shows the difference. A higher rate is refused: that
            needs a supplementary invoice.
          </li>
          <li>
            The "Totals" panel on the right shows the taxable value, GST,
            round off and total. Add files (photo of damaged goods, the
            customer's mail) under "Attachments".
          </li>
          <li>
            Click "Save" to keep the draft, or "Submit". Lines left at 0 (or at
            the bill rate) are dropped on Submit. The page stays open and says
            "Submitted as …" with the date and time.
          </li>
        </ol>
        <h3>What it posts</h3>
        <p>
          The "Ledger Posting" box shows what Submit will post on a draft, and
          what was posted once submitted. Every type debits each item group's
          "Sales Ledger" with the taxable value and "Output CGST" and "Output
          SGST" (or "Output IGST") with the tax, and credits the customer with
          the total; "Round Off" takes the rounding to the rupee. For goods
          that come back it also debits the item group's "Stock Ledger" and
          credits its "COGS/Expense Ledger" with the cost they left at. For goods
          not coming back, their cost stays in Cost of Goods Sold. If an item
          group has no ledger set, Submit shows the usual popup with "Set
          ledgers" or "Ask to set"; the draft is kept.
        </p>
        <p>
          "Invoice Due After This Note" shows the invoice's due dates less
          its credit notes, taken off the latest due date first. A return does
          not change the sales order's delivered quantity: if the customer
          wants the goods again, send them on a new delivery.
        </p>
        <h3>e-Invoice</h3>
        <p>
          A credit note to a registered customer needs an e-invoice, as the
          invoice did. After Submit, click "Download e-Invoice JSON" in the
          "e-Invoice" box and upload it on the e-invoice portal. Then click
          "Enter Portal Numbers" and either "Read Portal File" (pick the JSON
          the portal gives back) or type the "IRN", "Ack No", "Ack Date" and
          "Signed QR Code"; click "Save". The QR code prints on the credit
          note. No e-way bill is made for a credit note.
        </p>
        <h3>After Submit</h3>
        <p>
          "Print ▾" holds "Credit Note" (the GST credit note to send to the
          customer) and "Download PDF". "Create ▾" will hold the refund
          payment once it is built. "Cancel Credit Note" (with a reason)
          reverses the entries, and takes goods that came back out of stock
          again. If the e-invoice was made, cancel it on the portal too.
        </p>
        <h3>Find the credit notes</h3>
        <p>
          Click "Entry", point at "Sales" and click "Credit Note". Pick
          "Draft", "Submitted", "Cancelled" or "All" in the box above the list;
          every column has its own "Search" box. Click a credit note to see it
          at the right with "Open" and "Print". Who may see or make credit
          notes: people whose role may see or make sales entries.
        </p>
      </>
    ),
  },
  {
    id: "stock-reports",
    title: "Stock reports",
    summary:
      "What is in stock on any day, by item, batch and bin, and every move of one item in and out.",
    body: (
      <>
        <p>
          Open them from "Reports" in the top menu. They show the company picked
          at the top right and read straight from the stock ledger, so they
          always agree with the submitted entries. Anyone whose role may see
          stock can open them. Each has the "Actions ▾" button with "Print" and
          "Download PDF".
        </p>
        <h3>Stock Summary</h3>
        <ul>
          <li>
            "As On" is the day the stock is counted at the end of; it starts at
            today.
          </li>
          <li>
            Each line is one item in one batch in one bin: "Item No", "Item
            Name", "Batch", "Warehouse", "Bin", "Unit", "Quantity", "Rate ₹" (the
            average cost) and "Value ₹". The warehouse shows the branch's name
            as typed on the branch, and a bin shows its own name alone, without
            its rack. This is how bins read
            everywhere in MyERP, on screens and prints.
          </li>
          <li>
            Type in the "Search" box under any heading to keep only the lines
            that match, for example a batch number or a warehouse. Searches in
            several columns all have to match.
          </li>
          <li>
            "Total" adds up the lines shown, so a search gives its own total.
            The quantity total shows when all those lines are in one unit.
          </li>
          <li>
            The value is what the goods were received at: the order rate before
            GST plus any charge ticked to be added to stock cost. A supplier's
            bill at another rate changes it from the bill's date.
          </li>
          <li>
            Click an item number to open its Stock Ledger in a new tab. Opened
            from the Items screen, the list shows that one item; "Show all
            items" brings back the rest.
          </li>
        </ul>
        <h3>Stock Ledger</h3>
        <ul>
          <li>
            Pick the "Item", and the "From" and "To" dates (From starts at 1
            April of the year). "Warehouse", "Batch" and "Bin" narrow it to one
            place or one batch.
          </li>
          <li>
            The first line is the "Opening" balance on the From date. Each line
            after it is one entry: its date, its number (click it to open the
            entry in a new tab), the batch and bin, the quantity "In" or "Out",
            and the "Balance" and "Value ₹" after it. The last line is the
            "Closing" balance.
          </li>
          <li>
            A cancelled entry shows twice: once as made and once, greyed and
            marked "(cancelled)", taking it back out. A supplier's bill at a
            different rate shows as a "(rate change)" line that changes only
            the value.
          </li>
        </ul>
        <Note>
          To check a goods receipt: the Stock Summary should show the accepted
          quantity of each item in the bins it was put away in, and the Stock
          Ledger of the item should list the receipt's number with the same
          quantities.
        </Note>
      </>
    ),
  },
  {
    id: "accounts-reports",
    title: "Accounts reports",
    summary:
      "The Trial Balance of every ledger under its groups, and the Ledger Statement of one ledger with each entry.",
    body: (
      <>
        <p>
          Open them from "Reports" in the top menu. They show the company picked
          at the top right and read straight from the books, so every submitted
          entry is in them. Anyone whose role may see accounts can open them.
          Each has the "Actions ▾" button with "Print" and "Download PDF".
        </p>
        <h3>Trial Balance</h3>
        <ul>
          <li>
            "From" starts at the first day of the financial year and "To" at
            today. The "Opening ₹" of each ledger is the opening balance entered
            on it plus everything posted before From; "Debit ₹" and "Credit ₹"
            are what was posted between From and To; "Closing ₹" is the balance
            on To. Balances show "Dr" or "Cr".
          </li>
          <li>
            Ledgers sit under their ledger groups, and each group shows the
            totals of everything under it. Fold a group with its arrow, or use
            "Show levels" to fold the list to a depth. Ledgers with no balance
            and no entries are left out.
          </li>
          <li>
            "Total" at the bottom must show the same debits and credits. If they
            differ, a red line under the list says by how much: the opening
            balances entered on the ledgers do not add up.
          </li>
          <li>Click a ledger to open its Ledger Statement in a new tab.</li>
        </ul>
        <h3>Ledger Statement</h3>
        <ul>
          <li>Pick the "Ledger", and the "From" and "To" dates.</li>
          <li>
            The first line is the "Opening" balance on From. Each line after it
            is one entry: its date, its number (click it to open the entry in a
            new tab), "Particulars" (the ledgers on the other side of that
            entry), the debit or credit, and the "Balance ₹" after it. The last
            line is the "Closing" balance with the totals of the period.
          </li>
          <li>
            A cancelled entry shows twice: once as made and once, greyed and
            marked "(cancelled)", taking it back out.
          </li>
        </ul>
        <Note>
          To check a goods receipt: its Stock ledger (set on the item's main
          item group) shows a debit and "Goods Received but Bills not Received"
          shows the same amount as a credit, with the receipt's number on both.
          The amount is the order rate before GST, plus any charge added to
          stock cost.
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
