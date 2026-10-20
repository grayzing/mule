# MULE

**M**obile **U**nit for **L**ogging and **E**xtraction

![Image](basic_idea.png)

This is the basic idea of the project. Farmers and agriculture people in general typically have to physically go into the field to extract soil data loggers. This project has people install a datalogger in the field first, and simply fly a drone over the datalogger to extract the soil data, negating the need to go into the field and search for the datalogger.

This is the architecture. This implementation uses a custom solar-powered datalogger using a Raspberry Pi, with SDI-12 soil sensors (in our case, a few Acclima sensors). The datalogger accumulates data from the soil sensors into a `.csv` file. When it detects the AP of the Raspberry Pi, it connects to the Raspberry Pi, and if its signal is sufficient, it'll send the `.csv` over to an HTTP endpoint hosted on the Raspberry Pi. If the transmission is successful, it deletes the local `.csv` and resumes accumulation.

This project was done with support by UCR's Digital Agriculture Fellowship.

![Image](architecture.png)

Above is the general architecture of the project. The exact scripts and setup can be found in `drone/` and `datalogger/` respectively.
