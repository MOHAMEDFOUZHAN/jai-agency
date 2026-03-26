# Logic Flow & Connectivity Diagram

This diagram represents the data flow and stock logic as requested.

```mermaid
flowchart TD
    %% Define Styles
    classDef add fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef sub fill:#ffebee,stroke:#b71c1c,stroke-width:2px;
    classDef doc fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef view fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;

    %% Nodes
    Stock[(Inventory / Stock)]
    
    subgraph Inbound [Inbound Flow]
        Purchase[Purchase]:::add
        SaleReturn[Sale Return]:::add
    end

    subgraph Outbound [Outbound Flow]
        Sale[Sale]:::sub
        PurchaseReturn[Purchase Return]:::sub
    end

    subgraph Documents [Financial Documents]
        Invoice[Invoice / Bills]:::doc
        SalesRecords[Sales Records]:::doc
        Credit[Credit / Adjustment]:::doc
    end

    Preview[Preview]:::view

    %% Logic Connections
    Purchase -->|Adds (+)| Stock
    SaleReturn -->|Return (+)| Stock

    Sale -->|Deducts (-)| Stock
    PurchaseReturn -->|Return (-)| Stock

    %% specific relations requested
    Credit -->|Connects to| Invoice
    Credit -->|Connects to| SalesRecords

    Sale -->|Generates| Invoice
    Preview -.->|Views| Invoice
```
