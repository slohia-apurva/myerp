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
          Wherever you pick a group, state, currency, credit term, salesman or
          an existing customer or supplier, click the box and start typing: the
          list narrows to what matches (type any part of the name, in any
          order). Use the up and down arrow keys and Enter, or click the one you
          want. Press Esc to close the list without changing it.
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
            "Credit terms", "Items" and "Units". Ledger groups and ledgers open
            for the company you are working in. Owners also see "Admin", which
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
              "Warehouse",
              'Tick "This branch is a warehouse" when goods are stored here. It then gets a section on the "Warehouses" tab for its racks, bins and areas.',
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
            Click "Add credit terms" and give them a name, such as "30% advance,
            70% in 15 days".
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
          Once a customer or supplier uses credit terms, their parts cannot be
          changed (you can still rename them or add notes). Add new credit terms
          and move the customer to them instead.
        </p>
        <p>
          The list shows each term in words and how many parties use it. Credit
          terms are never deleted: click "Edit" and then the "Disable" button to
          stop offering them to new parties ("Enable" brings them back). Parties
          that already have them keep them.
        </p>
        <p>
          To change many at once, use "Actions" at the top of the screen. See
          the chapter "Import, export and print".
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
          the panels on the right. Type in the search box to find an item by
          name, number, HSN or barcode.
        </p>
        <p>
          Double-click an item, press Enter, or click "Open" to see its own
          page. It has folding sections: "General", "Sales", "Purchase", "GST
          Rates", "Stock And Quality", "Units Of Measure" and "Connections".
          Click a section's title bar to open or close it; a closed section
          still shows a line of its main values. "Switches" and "Activity" are
          in the panels on the right. People who may change items also see
          "Edit" and "Duplicate" in the green bar; "Close" goes back to the
          list.
        </p>
        <p>
          "Add item", "Edit" and "Duplicate" open the form in a new browser tab
          with the whole width, so the list stays open in the first tab.
          "Save" or "Cancel" closes the new tab and the list refreshes and
          selects the item. If you opened the form link by hand, the tab cannot
          close itself and shows the list instead.
        </p>
        <h3>Add an item</h3>
        <ol>
          <li>
            Click "Masters" in the top menu, then "Items", then "Add item". The
            form has tabs: "General", "Sales", "Purchase", "GST rates", "Stock
            and quality", "Units of measure" and "Connections" (empty for now: it
            will list the documents that use the item).
          </li>
          <li>
            The large "Item name" at the top is a box you can click and change at
            any time; the "Item number" beside it is given when you save. Fields
            marked with a red * must be filled in. Under "General", choose
            "Goods or service", pick the "Item group"
            (it must be filled in; see the chapter "Item groups"), pick the "HSN code" from the list (it must be filled in, and a code that is not in the list is refused; its "HSN description" shows beside it; for a service use its SAC code),
            the "Default unit of measure" (the unit stock is counted in, such as
            Packet) and the "Brand" (see the chapter "Brands"). In the "Switches" box, tick "Disabled" to stop using the item, and untick "Allow
            purchase" or "Allow sales" where the item is not bought or sold.
            "Maintain stock" is separate from goods or service: untick it for an
            item whose stock is not to be kept, and tick it for a service whose
            stock is. For a service that keeps stock (job work, where the
            customer's goods are processed and sent back), two more boxes
            appear: "Delivery HSN code" and its description. Pick the HSN code
            of the goods there; it goes on the delivery challan and e-way
            bill, while the "HSN code" above (the service code) goes on the
            invoice and e-invoice. The boxes disappear when the item is goods
            or does not keep stock. "Notes" are in the box below.
          </li>
          <li>
            On the "Sales" tab, write the "Sales description" customers should
            see on quotations, orders and bills, and pick the "Default sales
            unit" (for example Carton). Fill in the "MRP (₹)", the "USP" and the
            "Batch No" printed on the pack. "Best before" is a number with
            "Days" or "Months": a manufacturing order adds it to the
            manufacturing date to work out the best-before date. On the
            "Purchase" tab write the "Purchase description" for suppliers, pick
            the "Default purchase unit", and fill in the "Lead time in days",
            "Safety stock qty", "Minimum order qty" and "Max stock qty" (the
            quantities are in the item's default unit; the maximum cannot be
            below the safety stock). The default units are picked from the
            item's own units, so add a unit on the "Units of measure" tab
            first. Left blank, the stock unit is used.
          </li>
          <li>
            On the "GST rates" tab, click "Add rate" and fill in "From" (the
            date the rate starts) and "GST rate (%)". When the law changes, do
            not change the old row: click "Add rate" again and give the new rate
            with its start date. A bill takes the rate in force on the bill
            date, and the item's details mark today's rate "In force".
          </li>
          <li>
            On the "Stock and quality" tab, choose the "Default material request
            type": "Manufacture" if the item is made in-house, "Purchase" if it
            is bought, or "Customer Provided" if the customer supplies it (it is
            what a material request for the item starts as, and can be left
            "Not set"). Tick "Track batches" if you must
            follow batch numbers, and tick "Quality check on receipt" if goods
            must be checked when they arrive.
          </li>
          <li>
            On the "Units of measure" tab, click "Add unit" for each other unit
            the item is bought, sold or moved in. The stock unit is added for
            you. For a Carton, say it contains 4 of "Inner box", and for an
            Inner box that it contains 6 of "Packet"; the "= Packet" column then
            shows 24 by itself. Fill in the length, breadth and height in
            centimetres, the net and gross weight in kilograms, and the barcode.
            Volume is worked out from the size. Under "Used for", tick where
            each unit is the usual one.
          </li>
          <li>Click "Save".</li>
        </ol>
        <Note>
          A missing size is only a reminder under the table, not an error, so
          you can add an item before it has been measured. "Whole numbers only"
          on a unit (for example cartons) will stop a quantity such as 2.5 on
          documents. A barcode can belong to one item only.
        </Note>
        <p>
          Items are never deleted: click "Edit", tick "Disabled" and "Save" to
          stop using one (untick it to bring it back). Use "Duplicate" to start
          a new item from an existing one; barcodes are not copied.
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
          description.
        </p>
        <p>
          On the item form, the "HSN" box searches this list as you type. Type a
          few digits, or words such as "turmeric", and click the code you want.
          A code that is not in the list can still be typed in. If a code you
          need is missing, tell us and it will be added for everyone.
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
          The screen has three tabs. "Customers" lists every customer group
          (tenant) with its status. "Shared lists" shows each central list with
          the number of rows in it (click "Open" to look inside) and the "Load
          lists from a file" box. "Couriers" holds the courier list and the
          requests customers have sent.
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
          <li>Click "Save".</li>
        </ol>
        <p>
          Couriers are never deleted: click "Edit" and then "Disable" to stop
          offering one; transporters already using it keep it.
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
    id: "brands",
    title: "Brands",
    summary:
      "The brand names that items are sold under, picked on the item's General tab.",
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
            Click "Add brand", then give the "Name" (for example Apurvam) and,
            if you like, "Notes".
          </li>
          <li>Click "Save".</li>
        </ol>
        <p>
          Brand names must be different, whatever the capital letters. The
          "Items" column shows how many items carry each brand. Brands are never
          deleted: click "Edit" and then the "Disable" button to stop offering a
          brand ("Enable" brings it back); items already using it keep it. To
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
            group to add one under it. Give the "Name" (for example Whole
            spices) and, if you like, "Notes".
          </li>
          <li>
            To place a group elsewhere, change the "Under" box. A group cannot
            go under itself or a group below it.
          </li>
          <li>Click "Save".</li>
        </ol>
        <p>
          The arrow beside a group folds or opens the groups under it, and "Show
          levels" opens the tree to the depth you pick. The "Items" column
          counts the items in a group and in the groups below it.
        </p>
        <p>
          Once an item sits in a group, or in a group below it, that group
          cannot be moved under another group, so reports keep their meaning.
          Names and notes can still be changed. Names must be different whatever
          the capital letters. Groups are never deleted: click "Edit" and then
          the "Disable" button to stop offering a group ("Enable" brings it
          back); items already in it keep it. To change many groups at once, use
          "Actions" (see "Import, export and print"); in an import file, list a
          group before the groups under it.
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
            Click "Add unit", then give the "Name" (for example Drum) and a
            "Short name" (for example drm).
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
          <li>Click "Save".</li>
        </ol>
        <p>
          Once an item uses a unit, its "GST unit code" and "Whole numbers only"
          cannot be changed, so old records keep their meaning. The name can
          still be corrected.
        </p>
        <p>
          Wherever a unit is picked or shown in the masters, such as on an item,
          it reads with its short name in brackets, for example "Kilogram (Kg)".
          Entry screens and reports will show the short name alone ("Kg").
          Names and short names must be different from each other, whatever the
          capital letters. Units are never deleted: click "Edit" and then the
          "Disable" button to stop offering a unit ("Enable" brings it back).
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
          at the foot of each page.
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
          A physical warehouse is a branch of the company. Inside it there are
          racks, a rack holds bins, and a bin is a physical location where stock
          is kept. Apart from the bins, the warehouse has areas, which are named
          zones such as Receiving, Production and Despatch.
        </p>
        <h3>Make a branch a warehouse</h3>
        <ol>
          <li>Open the company and click the "Branches" tab.</li>
          <li>Click "Add branch", or "Edit" on a branch.</li>
          <li>Tick "This branch is a warehouse" and click "Save".</li>
        </ol>
        <h3>Add racks, bins and areas</h3>
        <ol>
          <li>Click the "Warehouses" tab. Each warehouse has its own box.</li>
          <li>
            Click "Add rack" and give the rack a name, for example R1, then
            click "Save".
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
          the arrow beside a rack to fold or show its bins. Racks, bins and
          areas are never deleted: click "Edit" and then "Disable". A rack can
          be disabled only after its bins are disabled. A branch that has racks,
          bins or areas stays a warehouse. To add many at once, use "Actions" at
          the top of the Warehouses tab (see "Import, export and print"); in the
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
          see those ledgers.
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
          in "Under". Groups are never deleted: click "Disable" to stop using
          one ("Enable" brings it back). A group can be disabled only when the
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
            to find a ledger by name or bank account number.
          </li>
          <li>
            <strong>The side panel on the right</strong> shows the ledger you
            click: its group and nature, opening balance (with the foreign
            currency amount and rate if it has one), currency, whether it is
            kept bill by bill, bank details, opening bills and notes. After
            clicking a ledger, the ↑ and ↓ keys move through the list. On a
            phone the panel shows above the list.
          </li>
          <li>
            <strong>Activity</strong> at the bottom of the side panel shows
            every change made to that ledger: who, when, and the old and new
            values (see "Change log").
          </li>
        </ul>
        <h3>Add a ledger</h3>
        <ol>
          <li>Click "Add ledger". The form opens in the side panel.</li>
          <li>Type the name and choose the group it goes under.</li>
          <li>
            If the company uses foreign currencies, choose the ledger's
            currency.
          </li>
          <li>
            For a bank ledger, fill in the bank, account number, IFSC and
            branch.
          </li>
          <li>Enter the opening balance (see below) and click "Save".</li>
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
          Click a ledger in the list and its details show on the right in boxes:
          "Balance", "GST", "Credit", "Addresses" and "Contacts" (for a customer
          or supplier), with the change log, "Activity", below.
        </p>
        <ul>
          <li>
            To add a party another company already deals with, click "Add
            ledger", choose Sundry Debtors or Sundry Creditors, and pick it
            under "Existing customer or supplier". Its details fill in; enter
            this company's credit limit and opening balance, and click "Save".
          </li>
          <li>
            A firm that both buys from and sells to this company can have two
            ledgers here: one under Sundry Debtors and one under Sundry
            Creditors. Add the second one with "Add ledger", choose the other
            group, and pick the firm under "Existing customer or supplier".
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
          A customer or supplier form has tabs along the top: "General", "GST
          and credit", "Addresses", "Contacts", "Documents", "Labels" (customers only) and "Opening balance". "Save" and
          "Cancel" are at the bottom of every tab. On the "General" tab, "Under
          group" is followed by the "Customer number" (or "Vendor number") and
          then the "GSTIN". The number is given automatically when you Save
          (CUST-00001, VEND-00001 and so on, running on across the group); a
          party that is a customer and a vendor (in one company or in different
          ones) has both. You may type your own number over it, but no two
          parties can share one. Search for a ledger by its number in the
          Ledgers list. Typing the GSTIN makes the party a registered one and
          fills in the state and PAN; the state decides the place of supply on
          invoices. "Fetch details" asks the GST portal for the name and address
          and fills them in. The registered address goes on the "Addresses" tab,
          named after the party; you can rename it, for example "Head office".
          It also warns if the GSTIN is not "Active" (cancelled or suspended).
          If the lookup is not available (the key is not set, the credits are
          used up, or the GST system is down) it says so, and you enter the
          details by hand.
        </p>
        <p>
          The "GST and credit" tab has two boxes, "GST" and "Credit". Together
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
              "Salesman or Purchaser",
              "The person in this company who looks after the customer (Salesman) or buys from the supplier (Purchaser). Other companies can choose someone else for the same party.",
            ],
          ]}
        />
        <p>
          On the "Addresses" tab, click "+ Add address" for each place the party
          has: office, godown, shop. Give each a name, and tick which one is the
          default billing address and which the default shipping address;
          documents pick these first. If the party is registered in another
          state too, enter that GSTIN on that address, then click "Fetch
          details" beside it: the address's name, state, address and PIN code
          are filled in from the GST portal, and you can change any of them.
        </p>
        <p>
          Type the six digits of the "PIN code" and MyERP looks it up in the
          central list: the "City" box is filled in if it was empty, and so is
          the "State" on a party address. The couriers that deliver to that PIN
          are shown under the box (with "out of delivery area" where it
          applies). You can change the city or state if the list is wrong.
          Company and branch forms have a "City" box too, filled from the PIN
          the same way, but their state is not changed. For an overseas party,
          the "Country" box is a type-to-search list of countries.
        </p>
        <p>
          On the "Contacts" tab, click "+ Add contact" for each person you deal
          with: the owner, the purchase manager, accounts. Give each a name, and
          add their designation, phone and email. Under "Contact type", tick
          what each person is for: "Main" (the one to call first; only one per
          party), "Accounting", "Shipping", "Purchase" or "Sales". One person
          can have several types. When MyERP sends automated emails during
          transactions, it will send each to the contacts of the right type. The
          tab names show how many addresses and contacts the party has. If you
          click "Save" while a required field on another tab is empty, MyERP
          opens that tab and points to the field.
        </p>
        <p>
          On the "Documents" tab, keep the papers of the customer or supplier:
          its GST certificate, PAN card, FSSAI licence, MSME / Udyam
          registration, agreements and a cancelled cheque. The tab opens once
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
          The "Labels" tab, which only customers have, is empty for now. It will hold the label format for
          each item the customer buys (one format for this customer and item A,
          another for item B), used when labels are printed for a despatch.
        </p>
        <p>
          Clicking a party shows its details, addresses and contacts in the side
          panel.
        </p>
        <h3>Opening balances</h3>
        <p>
          The opening balance is the balance on the date the company's books
          begin. Enter the amount and choose Dr or Cr. For a ledger in a foreign
          currency, enter the amount in that currency and the rate; the rupee
          amount is worked out for you.
        </p>
        <p>
          For customers and suppliers, the opening balance is on the "Opening
          balance" tab. Tick "Maintain balances bill by bill" there and enter
          each unpaid bill with its reference, date, due date and amount. The
          opening balance is then the total of the bills. Bills must be dated
          before the books begin.
        </p>
        <Note>
          Ledgers are never deleted, so past entries always have their account.
          When a ledger is no longer needed, click "Edit" and then "Disable"; it
          then cannot be used in new entries. "Enable" brings it back.
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
        <h3>Add a transporter</h3>
        <ol>
          <li>
            Pick the company at the top right, then click "Masters" in the top
            menu, then "Transporters".
          </li>
          <li>Click "Add transporter".</li>
          <li>Fill in the form (see below) and click "Save".</li>
        </ol>
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
          sales invoice, not from this form. API keys and passwords are not kept
          here either; they are set up separately when a courier is connected.
          Once a shipment has been entered against a transporter, its "Courier
          in MyERP's list" and "Service" cannot be changed. The name, GSTIN and
          notes can still be corrected. Transporters are never deleted: click
          "Edit" and then "Disable" to stop offering one ("Enable" brings it
          back).
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
          <li>Enter their email (their Google account) and full name.</li>
          <li>Tick their roles. Only an Owner can make someone an Owner.</li>
          <li>
            Tick the companies they may work in. None ticked means all
            companies.
          </li>
          <li>Click "Save".</li>
        </ol>
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
